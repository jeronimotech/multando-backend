"""WhatsApp webhook handler: bridges incoming messages to the shared chatbot engine.

Manages WhatsApp-specific concerns (message parsing, image download, Redis
conversation state) and delegates AI processing to the shared engine at
``app.services.chatbot.engine.process_message``.
"""

import base64
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker
from app.core.redis import get_redis
from app.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageType,
    User,
)
from app.services.chatbot.engine import process_message
from app.services.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

# Redis key prefix for mapping phone numbers -> conversation IDs
WA_CONV_PREFIX = "wa_conv:"
WA_CONV_TTL = 1800  # 30 minutes


async def handle_incoming(body: dict[str, Any], whatsapp: WhatsAppClient) -> None:
    """Process a full WhatsApp webhook payload.

    Extracts messages from the payload and routes each one through
    the shared chatbot engine.

    Args:
        body: The parsed webhook JSON body from Meta.
        whatsapp: WhatsApp client instance for sending replies.
    """
    for entry_item in body.get("entry", []):
        for change in entry_item.get("changes", []):
            value = change.get("value", {})

            for message in value.get("messages", []):
                await _process_single_message(message, value, whatsapp)

            # Log status updates (delivery/read receipts)
            for status_update in value.get("statuses", []):
                logger.debug(
                    "WhatsApp status update: message=%s, status=%s, recipient=%s",
                    status_update.get("id", ""),
                    status_update.get("status", ""),
                    status_update.get("recipient_id", ""),
                )


async def _process_single_message(
    message: dict[str, Any],
    value: dict[str, Any],
    whatsapp: WhatsAppClient,
) -> None:
    """Parse a single WhatsApp message and route it through the chatbot engine.

    Steps:
    1. Extract phone number and contact name.
    2. Mark the message as read (best-effort).
    3. Look up or create a User by phone number.
    4. Look up or create a Conversation (tracked via Redis for fast lookup).
    5. Save the inbound message to the DB.
    6. Call the shared ``process_message()`` engine.
    7. Send the AI reply back via WhatsApp.
    """
    phone_number = message.get("from", "")
    message_id = message.get("id", "")
    msg_type = message.get("type", "")

    if not phone_number:
        logger.warning("WhatsApp message without phone number: %s", message_id)
        return

    # Extract contact name
    contacts = value.get("contacts", [])
    contact_name: str | None = None
    if contacts:
        profile = contacts[0].get("profile", {})
        contact_name = profile.get("name")

    # Mark as read (best-effort, don't block on failure)
    try:
        await whatsapp.mark_as_read(message_id)
    except Exception as exc:
        logger.warning("Failed to mark message %s as read: %s", message_id, exc)

    # Extract text content and optional image data
    text_content, image_base64, image_media_type = await _extract_message_content(
        message, msg_type, whatsapp
    )

    if text_content is None:
        # Unsupported message type - nothing to process
        return

    # Database operations: get/create user, conversation, save message, call engine
    try:
        async with async_session_maker() as db:
            # 1. Get or create user by phone number
            user = await _get_or_create_user(db, phone_number, contact_name)

            # 2. Get or create conversation (Redis-cached for speed)
            conversation = await _get_or_create_conversation(db, user, phone_number)

            # 3. Save the inbound message
            msg_type_enum = MessageType.IMAGE if image_base64 else MessageType.TEXT
            metadata = None
            if image_base64:
                metadata = {
                    "image_base64": image_base64,
                    "image_media_type": image_media_type,
                }

            inbound_msg = Message(
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                content=text_content,
                message_type=msg_type_enum,
                message_metadata=metadata,
            )
            db.add(inbound_msg)
            await db.flush()

            # 4. Call the shared chatbot engine
            ai_result = await process_message(
                user_id=user.id,
                conversation_id=conversation.id,
                message=text_content,
                image_base64=image_base64,
                image_media_type=image_media_type,
                db=db,
            )

            await db.commit()

            # 5. Send AI reply via WhatsApp
            reply_text = ai_result["message"].get("content", "")
            if reply_text:
                await whatsapp.send_text(phone_number, reply_text)
                logger.info(
                    "WhatsApp reply sent to %s (length=%d)",
                    phone_number,
                    len(reply_text),
                )

    except Exception as exc:
        logger.error(
            "Error processing WhatsApp message from %s: %s",
            phone_number,
            exc,
            exc_info=True,
        )
        # Send a friendly error message
        try:
            await whatsapp.send_text(
                phone_number,
                "Lo siento, algo salio mal. Por favor intenta de nuevo. "
                "/ Sorry, something went wrong. Please try again.",
            )
        except Exception as send_exc:
            logger.error("Failed to send error message: %s", send_exc)


async def _extract_message_content(
    message: dict[str, Any],
    msg_type: str,
    whatsapp: WhatsAppClient,
) -> tuple[str | None, str | None, str]:
    """Extract text content and optional image data from a WhatsApp message.

    Args:
        message: Raw WhatsApp message dict.
        msg_type: Message type string (text, image, location, etc.).
        whatsapp: WhatsApp client for downloading media.

    Returns:
        Tuple of (text_content, image_base64, image_media_type).
        text_content is None for unsupported message types.
    """
    image_base64: str | None = None
    image_media_type: str = "image/jpeg"

    if msg_type == "text":
        text = message.get("text", {}).get("body", "")
        return text, None, image_media_type

    if msg_type == "image":
        image_data = message.get("image", {})
        media_id = image_data.get("id", "")
        mime_type = image_data.get("mime_type", "image/jpeg")
        caption = image_data.get("caption", "")

        try:
            image_bytes = await whatsapp.download_media(media_id)
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            image_media_type = mime_type
        except Exception as exc:
            logger.error("Failed to download image %s: %s", media_id, exc)
            return (
                "User sent an image but it could not be downloaded. "
                "Ask them to resend it.",
                None,
                image_media_type,
            )

        text = caption or (
            "User sent an image. Please analyze it for traffic violations."
        )
        return text, image_base64, image_media_type

    if msg_type == "video":
        return (
            "User sent a video (cannot be analyzed). "
            "Ask them to send a photo instead.",
            None,
            image_media_type,
        )

    if msg_type == "location":
        loc = message.get("location", {})
        lat = loc.get("latitude", 0)
        lon = loc.get("longitude", 0)
        address = loc.get("address") or loc.get("name") or "unknown"
        return (
            f"User shared their location: latitude={lat}, "
            f"longitude={lon}, address={address}",
            None,
            image_media_type,
        )

    if msg_type == "interactive":
        interactive = message.get("interactive", {})
        reply = (
            interactive.get("button_reply")
            or interactive.get("list_reply")
            or {}
        )
        reply_title = reply.get("title", "unknown")
        reply_id = reply.get("id", "unknown")
        return (
            f"User selected: {reply_title} (id: {reply_id})",
            None,
            image_media_type,
        )

    # Unsupported type - still process it
    return (
        f"User sent an unsupported message type: {msg_type}.",
        None,
        image_media_type,
    )


async def _get_or_create_user(
    db: AsyncSession,
    phone_number: str,
    contact_name: str | None,
) -> User:
    """Look up a user by phone number, or create one for WhatsApp users.

    Args:
        db: Database session.
        phone_number: The user's phone number.
        contact_name: Optional display name from WhatsApp.

    Returns:
        The User record.
    """
    result = await db.execute(
        select(User).where(User.phone_number == phone_number)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-register WhatsApp users with a placeholder account
        user = User(
            phone_number=phone_number,
            full_name=contact_name or f"WhatsApp {phone_number[-4:]}",
            is_active=True,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("Auto-registered WhatsApp user: phone=%s, id=%s", phone_number, user.id)

    return user


async def _get_or_create_conversation(
    db: AsyncSession,
    user: User,
    phone_number: str,
) -> Conversation:
    """Get or create a conversation for a WhatsApp user.

    Uses Redis to cache the phone_number -> conversation_id mapping
    so we don't have to query the DB on every message.

    Args:
        db: Database session.
        user: The user record.
        phone_number: The user's phone number.

    Returns:
        The active Conversation record.
    """
    # Try Redis cache first
    try:
        r = await get_redis()
        cached_id = await r.get(f"{WA_CONV_PREFIX}{phone_number}")
        if cached_id:
            conv_id = int(cached_id)
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == conv_id,
                    Conversation.status == ConversationStatus.ACTIVE,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                # Refresh TTL
                await r.setex(
                    f"{WA_CONV_PREFIX}{phone_number}",
                    WA_CONV_TTL,
                    str(conv.id),
                )
                return conv
    except Exception as exc:
        logger.warning("Redis lookup failed for WhatsApp conversation: %s", exc)

    # Check DB for an active conversation
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.status == ConversationStatus.ACTIVE,
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    conv = result.scalar_one_or_none()

    if conv is None:
        # Create a new conversation
        conv = Conversation(
            user_id=user.id,
            phone_number=phone_number,
            status=ConversationStatus.ACTIVE,
        )
        db.add(conv)
        await db.flush()
        await db.refresh(conv)
        logger.info(
            "Created new WhatsApp conversation: user=%s, conv_id=%d",
            user.id,
            conv.id,
        )

    # Cache in Redis
    try:
        r = await get_redis()
        await r.setex(
            f"{WA_CONV_PREFIX}{phone_number}",
            WA_CONV_TTL,
            str(conv.id),
        )
    except Exception as exc:
        logger.warning("Failed to cache WhatsApp conversation in Redis: %s", exc)

    return conv
