"""Conversation endpoints for the Multando AI chatbot.

This module provides REST endpoints for managing conversations
and exchanging messages with the Claude-powered AI assistant.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models import (
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageType,
)
from app.schemas.conversation import (
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
    MessageSend,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _msg_to_schema(msg: Message) -> MessageResponse:
    """Convert a Message model to a MessageResponse schema."""
    return MessageResponse(
        id=msg.id,
        conversation_id=msg.conversation_id,
        direction=msg.direction.value,
        content=msg.content,
        message_type=msg.message_type.value,
        created_at=msg.created_at,
    )


def _conv_to_schema(conv: Conversation, include_messages: bool = False) -> ConversationResponse:
    """Convert a Conversation model to a ConversationResponse schema."""
    messages = []
    if include_messages and conv.messages:
        messages = [_msg_to_schema(m) for m in conv.messages]
    return ConversationResponse(
        id=conv.id,
        status=conv.status.value,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=messages,
    )


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new conversation",
    description="Start a new AI chat conversation for the authenticated user.",
)
async def create_conversation(
    _body: ConversationCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationResponse:
    """Create a new conversation.

    Args:
        _body: Empty body (no fields needed).
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The created ConversationResponse.
    """
    conv = Conversation(
        user_id=current_user.id,
        phone_number=current_user.phone_number or "",
        status=ConversationStatus.ACTIVE,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)

    await db.commit()
    return _conv_to_schema(conv)


@router.get(
    "",
    response_model=list[ConversationResponse],
    summary="List conversations",
    description="List all conversations for the authenticated user.",
)
async def list_conversations(
    current_user: CurrentUser,
    db: DbSession,
) -> list[ConversationResponse]:
    """List user's conversations.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        A list of ConversationResponse objects.
    """
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    )
    conversations = list(result.scalars().all())
    return [_conv_to_schema(c) for c in conversations]


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get conversation with messages",
    description="Get a specific conversation and its full message history.",
)
async def get_conversation(
    conversation_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> ConversationResponse:
    """Get a conversation with all messages.

    Args:
        conversation_id: ID of the conversation.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The ConversationResponse with messages.

    Raises:
        HTTPException: 404 if conversation not found or doesn't belong to user.
    """
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return _conv_to_schema(conv, include_messages=True)


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatResponse,
    summary="Send a message",
    description="Send a message in a conversation and receive an AI response.",
)
async def send_message(
    conversation_id: int,
    body: MessageSend,
    current_user: CurrentUser,
    db: DbSession,
) -> ChatResponse:
    """Send a message and get an AI response.

    1. Validates the conversation belongs to the user and is active.
    2. Saves the user message to DB.
    3. Calls the AI engine to process the message.
    4. Returns the AI response.

    Args:
        conversation_id: ID of the conversation.
        body: The message content and optional image.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        ChatResponse with the AI's reply and any tool calls used.

    Raises:
        HTTPException: 404 if conversation not found, 400 if conversation is closed.
    """
    # Validate conversation ownership
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if conv.status != ConversationStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation is no longer active",
        )

    # Save the user's inbound message
    metadata = None
    msg_type = MessageType.TEXT
    if body.image_base64:
        metadata = {
            "image_base64": body.image_base64,
            "image_media_type": body.image_media_type,
        }
        # Attach SDK evidence metadata when present
        if body.image_hash:
            metadata["image_hash"] = body.image_hash
        if body.image_signature:
            metadata["image_signature"] = body.image_signature
        if body.image_timestamp:
            metadata["image_timestamp"] = body.image_timestamp
        if body.image_latitude is not None:
            metadata["image_latitude"] = body.image_latitude
        if body.image_longitude is not None:
            metadata["image_longitude"] = body.image_longitude
        if body.device_id:
            metadata["device_id"] = body.device_id
        if body.capture_method:
            metadata["capture_method"] = body.capture_method
        msg_type = MessageType.IMAGE

    user_msg = Message(
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND,
        content=body.content,
        message_type=msg_type,
        message_metadata=metadata,
    )
    db.add(user_msg)
    await db.flush()

    # Process through AI engine
    from app.services.chatbot.engine import process_message

    try:
        ai_result = await process_message(
            user_id=current_user.id,
            conversation_id=conversation_id,
            message=body.content,
            image_base64=body.image_base64,
            image_media_type=body.image_media_type,
            evidence_metadata={
                "image_hash": body.image_hash,
                "image_signature": body.image_signature,
                "image_timestamp": body.image_timestamp,
                "image_latitude": body.image_latitude,
                "image_longitude": body.image_longitude,
                "device_id": body.device_id,
                "capture_method": body.capture_method,
            } if body.image_base64 else None,
            db=db,
        )
    except ValueError as exc:
        logger.exception("Chatbot engine error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception:
        logger.exception("Unexpected chatbot error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your message. Please try again.",
        )

    await db.commit()

    # Build response
    ai_msg_data = ai_result["message"]
    return ChatResponse(
        message=MessageResponse(
            id=ai_msg_data["id"],
            conversation_id=ai_msg_data["conversation_id"],
            direction=ai_msg_data["direction"],
            content=ai_msg_data["content"],
            message_type=ai_msg_data["message_type"],
            created_at=ai_msg_data["created_at"],
        ),
        tool_calls=ai_result.get("tool_calls", []),
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Close a conversation",
    description="Close/delete a conversation. Marks it as completed.",
)
async def delete_conversation(
    conversation_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Close a conversation by marking it as completed.

    Args:
        conversation_id: ID of the conversation to close.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        A success message.

    Raises:
        HTTPException: 404 if conversation not found.
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conv.status = ConversationStatus.COMPLETED
    await db.flush()
    await db.commit()

    return {"message": "Conversation closed successfully", "success": True}
