"""Core AI chatbot engine powered by Anthropic Claude.

This module orchestrates conversations with Claude, including tool calling
and image analysis, using existing Multando services for data operations.
"""

import base64
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models import (
    Conversation,
    ConversationStatus,
    Evidence,
    EvidenceType,
    Infraction,
    Message,
    MessageDirection,
    MessageType,
    Report,
    ReportStatus,
)
from app.schemas.report import (
    LocationSchema,
    ReportCreate,
    ReportSource,
    VehicleCategory,
)
from app.services.chatbot.system_prompt import SYSTEM_PROMPT
from app.services.chatbot.tools import TOOLS
from app.services.evidence_processor import EvidenceProcessor
from app.services.infraction import InfractionService
from app.services.report import ReportService
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

MODEL = settings.ANTHROPIC_MODEL
MAX_TOOL_ROUNDS = 5  # Prevent infinite tool-call loops

def _normalize_quick_replies(raw: list | None) -> list[dict]:
    """Coerce the send_reply tool's quick_replies into the API shape.

    Ensures every item has both label and value (value defaults to label)
    and drops anything malformed.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:4]:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        value = item.get("value")
        if not isinstance(value, str) or not value.strip():
            value = label
        out.append({"label": label.strip(), "value": value.strip()})
    return out


def _detect_media_type(b64_data: str, fallback: str = "image/jpeg") -> str:
    """Detect image media type from base64 data magic bytes."""
    try:
        raw = base64.b64decode(b64_data[:32])
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if raw[:2] == b'\xff\xd8':
            return "image/jpeg"
        if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
            return "image/webp"
        if raw[:3] == b'GIF':
            return "image/gif"
    except Exception:
        pass
    return fallback


def _get_client() -> anthropic.Anthropic:
    """Create an Anthropic client using the configured API key."""
    if not settings.ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY is not configured. "
            "Set it in .env or environment variables."
        )
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


async def _load_conversation_history(
    conversation_id: int,
    db: AsyncSession,
) -> list[dict]:
    """Load conversation messages and convert to Claude message format.

    Args:
        conversation_id: ID of the conversation.
        db: Async database session.

    Returns:
        A list of message dicts in Claude API format.
    """
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = list(result.scalars().all())

    claude_messages: list[dict] = []
    for msg in messages:
        role = "user" if msg.direction == MessageDirection.INBOUND else "assistant"
        content = msg.content or ""

        # Check if message has image metadata
        if msg.message_metadata and msg.message_metadata.get("image_base64"):
            img_b64 = msg.message_metadata["image_base64"]
            media_type = _detect_media_type(img_b64)
            claude_messages.append({
                "role": role,
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": msg.message_metadata["image_base64"],
                        },
                    },
                    {"type": "text", "text": content},
                ],
            })
        else:
            claude_messages.append({"role": role, "content": content})

    return claude_messages


async def _execute_tool(
    tool_name: str,
    tool_input: dict,
    user_id: UUID,
    db: AsyncSession,
    image_context: dict | None = None,
    report_source: str = "mobile",
) -> str:
    """Execute a tool call and return the result as a JSON string.

    Args:
        tool_name: Name of the tool to execute.
        tool_input: Input parameters for the tool.
        user_id: UUID of the current user.
        db: Async database session.
        image_context: Optional dict with image bytes and evidence metadata
                       from the current conversation for evidence processing.

    Returns:
        JSON string with the tool result.
    """
    try:
        if tool_name == "get_infractions":
            svc = InfractionService(db)
            infractions = await svc.list_all()
            return json.dumps(
                [
                    {
                        "id": i.id,
                        "code": i.code,
                        "name_es": i.name_es,
                        "name_en": i.name_en,
                        "category": i.category.value,
                        "severity": i.severity.value,
                        "points_reward": i.points_reward,
                        "multa_reward": float(i.multa_reward),
                    }
                    for i in infractions
                ],
                ensure_ascii=False,
            )

        elif tool_name == "get_vehicle_types":
            from app.models import VehicleType
            result = await db.execute(select(VehicleType))
            types = result.scalars().all()
            return json.dumps(
                [
                    {
                        "id": vt.id,
                        "code": vt.code,
                        "name_es": vt.name_es,
                        "name_en": vt.name_en,
                        "icon": vt.icon,
                        "requires_plate": vt.requires_plate,
                    }
                    for vt in types
                ],
                ensure_ascii=False,
            )

        elif tool_name == "create_report":
            svc = ReportService(db)
            report_data = ReportCreate(
                infraction_id=tool_input["infraction_id"],
                vehicle_plate=tool_input.get("plate_number"),
                vehicle_type_id=tool_input.get("vehicle_type_id"),
                vehicle_category=VehicleCategory.PRIVATE,
                source=ReportSource(report_source) if report_source in [s.value for s in ReportSource] else ReportSource.MOBILE,
                location=LocationSchema(
                    lat=tool_input["latitude"],
                    lon=tool_input["longitude"],
                ),
                incident_datetime=datetime.now(timezone.utc),
            )
            report = await svc.create(user_id, report_data)

            # Process evidence image if available in conversation context
            evidence_info: dict | None = None
            if image_context and image_context.get("image_bytes"):
                try:
                    processor = EvidenceProcessor(db)
                    ev_meta = image_context.get("evidence_metadata") or {}
                    result = await processor.verify_and_process(
                        image_bytes=image_context["image_bytes"],
                        timestamp=ev_meta.get("image_timestamp"),
                        latitude=ev_meta.get("image_latitude"),
                        longitude=ev_meta.get("image_longitude"),
                        signature=ev_meta.get("image_signature"),
                        device_id=ev_meta.get("device_id"),
                        image_hash=ev_meta.get("image_hash"),
                    )

                    # Upload watermarked image to storage
                    from app.services.whatsapp.media import MediaService

                    s3_key = f"evidence/{report.id}/{result.image_hash}.jpg"
                    evidence_url = await MediaService.upload_evidence(
                        s3_key, result.processed_image, "image/jpeg"
                    )

                    evidence = Evidence(
                        report_id=report.id,
                        type=EvidenceType.IMAGE,
                        url=evidence_url,
                        mime_type="image/jpeg",
                        file_size=len(result.processed_image),
                        capture_verified=result.verified,
                        image_hash=result.image_hash,
                        capture_signature=ev_meta.get("image_signature"),
                        capture_metadata={
                            "device_id": ev_meta.get("device_id"),
                            "capture_method": ev_meta.get("capture_method"),
                            "verification_reasons": result.reasons,
                        },
                    )
                    db.add(evidence)
                    await db.flush()

                    evidence_info = {
                        "verified": result.verified,
                        "image_hash": result.image_hash,
                        "reasons": result.reasons,
                    }
                except Exception:
                    logger.exception("Evidence processing failed for report %s", report.id)
                    evidence_info = {
                        "verified": False,
                        "error": "Evidence processing failed",
                    }

            await db.commit()

            response_data = {
                "success": True,
                "report_id": str(report.id),
                "short_id": report.short_id,
                "status": report.status.value,
                "message": f"Reporte {report.short_id} creado exitosamente.",
            }
            if evidence_info:
                response_data["evidence"] = evidence_info

            # Expose the abuse-warning flag so the chatbot prompt can
            # nudge users whose reports get rejected too often. The
            # reporter relationship is already eager-loaded on the
            # returned report, so reading the property is cheap.
            if report.reporter is not None and getattr(
                report.reporter, "rejection_rate_warning", False
            ):
                response_data["rejection_rate_warning"] = True

            return json.dumps(response_data, ensure_ascii=False)

        elif tool_name == "list_my_reports":
            svc = ReportService(db)
            page = tool_input.get("page", 1)
            reports, total = await svc.list_reports(
                page=page,
                page_size=10,
                reporter_id=user_id,
            )
            return json.dumps(
                {
                    "total": total,
                    "page": page,
                    "reports": [
                        {
                            "short_id": r.short_id,
                            "status": r.status.value,
                            "vehicle_plate": r.vehicle_plate,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "infraction": r.infraction.name_es if r.infraction else None,
                        }
                        for r in reports
                    ],
                },
                ensure_ascii=False,
            )

        elif tool_name == "get_report_status":
            svc = ReportService(db)
            report_id_str = tool_input["report_id"]
            # Try UUID first, then short_id
            report = None
            try:
                uuid_id = UUID(report_id_str)
                report = await svc.get_by_id(uuid_id)
            except ValueError:
                report = await svc.get_by_short_id(report_id_str)

            if not report:
                return json.dumps(
                    {"error": "Reporte no encontrado. / Report not found."},
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "short_id": report.short_id,
                    "status": report.status.value,
                    "vehicle_plate": report.vehicle_plate,
                    "created_at": report.created_at.isoformat() if report.created_at else None,
                    "infraction": report.infraction.name_es if report.infraction else None,
                    "verified_at": report.verified_at.isoformat() if report.verified_at else None,
                    "on_chain": report.on_chain,
                },
                ensure_ascii=False,
            )

        elif tool_name == "get_wallet_balance":
            svc = WalletService(db)
            try:
                wallet_info = await svc.get_wallet_info(user_id)
                return json.dumps(
                    {
                        "balance": float(wallet_info.balance),
                        "staked_balance": float(wallet_info.staked_balance),
                        "pending_rewards": float(wallet_info.pending_rewards),
                        "total_earned": float(wallet_info.total_earned),
                        "wallet_type": wallet_info.wallet_type,
                        "wallet_status": wallet_info.wallet_status,
                    },
                    ensure_ascii=False,
                )
            except ValueError:
                return json.dumps(
                    {"balance": 0, "message": "No se encontro billetera para este usuario."},
                    ensure_ascii=False,
                )

        elif tool_name == "analyze_evidence":
            # The analyze_evidence tool is a hint for the model to use its
            # vision capabilities on the image already in the conversation.
            # We return a confirmation so the model can describe findings.
            description = tool_input.get("image_description", "")
            return json.dumps(
                {
                    "status": "analyzed",
                    "message": (
                        "Image analysis complete. Use the description to "
                        "extract plate, vehicle type, and infraction details. "
                        "Ask the user to confirm or correct."
                    ),
                    "description": description,
                },
                ensure_ascii=False,
            )

        else:
            return json.dumps(
                {"error": f"Herramienta desconocida: {tool_name}"},
                ensure_ascii=False,
            )

    except Exception as exc:
        logger.exception("Error executing tool %s", tool_name)
        return json.dumps(
            {"error": f"Error al ejecutar {tool_name}: {str(exc)}"},
            ensure_ascii=False,
        )


async def process_message(
    user_id: UUID,
    conversation_id: int,
    message: str,
    image_base64: str | None = None,
    image_media_type: str = "image/jpeg",
    evidence_metadata: dict | None = None,
    report_source: str = "mobile",
    db: AsyncSession | None = None,
) -> dict:
    """Process a user message through the Claude AI engine.

    1. Load conversation history from DB.
    2. Build Claude messages array (with optional image).
    3. Call Claude with tools.
    4. If Claude calls a tool, execute it and feed result back.
    5. Loop until Claude gives a final text response.
    6. Save assistant message to DB.
    7. Return response dict.

    Args:
        user_id: UUID of the authenticated user.
        conversation_id: ID of the conversation.
        message: The user's text message.
        image_base64: Optional base64-encoded image for analysis.
        image_media_type: MIME type of the image.
        evidence_metadata: Optional SDK evidence metadata (hash, signature, etc.).
        db: Async database session.

    Returns:
        A dict with the assistant message and tool_calls used.
    """
    if db is None:
        raise ValueError("Database session is required")

    client = _get_client()

    # Load existing conversation history
    claude_messages = await _load_conversation_history(conversation_id, db)

    # Build image context for evidence processing during tool calls.
    # Use the current image if provided, otherwise look for the most recent
    # image in the conversation history stored in message metadata.
    image_context: dict | None = None
    if image_base64:
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception:
            image_bytes = None
        if image_bytes:
            image_context = {
                "image_bytes": image_bytes,
                "image_base64": image_base64,
                "evidence_metadata": evidence_metadata,
            }
    else:
        # Check conversation history for the most recent image with metadata
        image_context = await _find_latest_image_context(conversation_id, db)

    # Build the new user message
    if image_base64:
        # Auto-detect media type from image bytes
        detected_type = _detect_media_type(image_base64, image_media_type)

        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": detected_type,
                    "data": image_base64,
                },
            },
            {"type": "text", "text": message},
        ]
    else:
        user_content = message

    claude_messages.append({"role": "user", "content": user_content})

    # Tool call loop
    tool_calls_log: list[dict] = []

    for _round in range(MAX_TOOL_ROUNDS):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=claude_messages,
            )
        except anthropic.APIError as exc:
            logger.exception("Anthropic API error")
            # Save a friendly error as the assistant response
            error_text = (
                "Lo siento, estoy teniendo problemas tecnicos en este momento. "
                "Por favor intenta de nuevo en unos minutos. "
                "/ Sorry, I'm having technical issues right now. Please try again shortly."
            )
            assistant_msg = await _save_assistant_message(
                conversation_id, error_text, db
            )
            return {
                "message": _message_to_dict(assistant_msg),
                "tool_calls": [],
                "quick_replies": [],
            }

        # Check for a terminal send_reply tool use (structured response).
        # If present, that's the final answer — extract, save, return.
        if response.stop_reason == "tool_use":
            send_reply_block = next(
                (
                    b for b in response.content
                    if b.type == "tool_use" and b.name == "send_reply"
                ),
                None,
            )
            if send_reply_block is not None:
                msg_text = (send_reply_block.input.get("message") or "").strip()
                quick_replies = _normalize_quick_replies(
                    send_reply_block.input.get("quick_replies")
                )
                if not msg_text:
                    msg_text = (
                        "Listo. / Done."
                    )
                assistant_msg = await _save_assistant_message(
                    conversation_id, msg_text, db
                )
                return {
                    "message": _message_to_dict(assistant_msg),
                    "tool_calls": tool_calls_log,
                    "quick_replies": quick_replies,
                }

            # Non-terminal tool use: add assistant turn, execute tools,
            # feed results back.
            claude_messages.append({
                "role": "assistant",
                "content": response.content,
            })

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls_log.append({
                        "tool": block.name,
                        "input": block.input,
                    })
                    result_str = await _execute_tool(
                        block.name, block.input, user_id, db,
                        image_context=image_context,
                        report_source=report_source,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })

            claude_messages.append({"role": "user", "content": tool_results})

        else:
            # Claude ended the turn with plain text instead of calling
            # send_reply. Force a structured reply by pushing the text
            # back and requesting send_reply via tool_choice.
            stray_text = "".join(
                b.text for b in response.content if hasattr(b, "text")
            ).strip()

            claude_messages.append({
                "role": "assistant",
                "content": response.content,
            })
            claude_messages.append({
                "role": "user",
                "content": (
                    "Please wrap your previous response by calling the "
                    "send_reply tool with the same message and any "
                    "appropriate quick_replies."
                ),
            })

            try:
                forced = client.messages.create(
                    model=MODEL,
                    max_tokens=2048,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    tool_choice={"type": "tool", "name": "send_reply"},
                    messages=claude_messages,
                )
            except anthropic.APIError:
                logger.exception("Anthropic API error on forced send_reply")
                assistant_msg = await _save_assistant_message(
                    conversation_id, stray_text or "Listo.", db
                )
                return {
                    "message": _message_to_dict(assistant_msg),
                    "tool_calls": tool_calls_log,
                    "quick_replies": [],
                }

            forced_block = next(
                (
                    b for b in forced.content
                    if b.type == "tool_use" and b.name == "send_reply"
                ),
                None,
            )
            if forced_block is None:
                assistant_msg = await _save_assistant_message(
                    conversation_id, stray_text or "Listo.", db
                )
                return {
                    "message": _message_to_dict(assistant_msg),
                    "tool_calls": tool_calls_log,
                    "quick_replies": [],
                }

            msg_text = (forced_block.input.get("message") or stray_text).strip()
            quick_replies = _normalize_quick_replies(
                forced_block.input.get("quick_replies")
            )
            assistant_msg = await _save_assistant_message(
                conversation_id, msg_text, db
            )
            return {
                "message": _message_to_dict(assistant_msg),
                "tool_calls": tool_calls_log,
                "quick_replies": quick_replies,
            }

    # If we exhausted tool rounds without a send_reply, return a generic note.
    fallback_text = (
        "He procesado tu solicitud. Si necesitas algo mas, no dudes en preguntar."
    )
    assistant_msg = await _save_assistant_message(
        conversation_id, fallback_text, db
    )
    return {
        "message": _message_to_dict(assistant_msg),
        "tool_calls": tool_calls_log,
        "quick_replies": [],
    }


async def _find_latest_image_context(
    conversation_id: int,
    db: AsyncSession,
) -> dict | None:
    """Scan conversation messages for the most recent image with metadata.

    When ``create_report`` is called in a later turn than the one where the
    image was sent, we need to recover the image bytes and evidence metadata
    from the stored message.

    Args:
        conversation_id: ID of the conversation.
        db: Async database session.

    Returns:
        A dict with ``image_bytes``, ``image_base64``, and ``evidence_metadata``
        if found, otherwise None.
    """
    result = await db.execute(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.message_type == MessageType.IMAGE,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    msg = result.scalar_one_or_none()
    if not msg or not msg.message_metadata:
        return None

    meta = msg.message_metadata
    img_b64 = meta.get("image_base64")
    if not img_b64:
        return None

    try:
        image_bytes = base64.b64decode(img_b64)
    except Exception:
        return None

    return {
        "image_bytes": image_bytes,
        "image_base64": img_b64,
        "evidence_metadata": {
            "image_hash": meta.get("image_hash"),
            "image_signature": meta.get("image_signature"),
            "image_timestamp": meta.get("image_timestamp"),
            "image_latitude": meta.get("image_latitude"),
            "image_longitude": meta.get("image_longitude"),
            "device_id": meta.get("device_id"),
            "capture_method": meta.get("capture_method"),
        },
    }


async def _save_assistant_message(
    conversation_id: int,
    content: str,
    db: AsyncSession,
) -> Message:
    """Save an assistant (outbound) message to the database.

    Args:
        conversation_id: ID of the conversation.
        content: The assistant's text content.
        db: Async database session.

    Returns:
        The created Message object.
    """
    msg = Message(
        conversation_id=conversation_id,
        direction=MessageDirection.OUTBOUND,
        content=content,
        message_type=MessageType.TEXT,
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    return msg


def _message_to_dict(msg: Message) -> dict:
    """Convert a Message model to a serializable dict.

    Args:
        msg: The Message model instance.

    Returns:
        A dict matching the MessageResponse schema.
    """
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "direction": msg.direction.value,
        "content": msg.content,
        "message_type": msg.message_type.value,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
