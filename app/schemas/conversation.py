"""Conversation and chat message schemas for the AI chatbot."""

from datetime import datetime

from app.schemas.base import BaseSchema


class ConversationCreate(BaseSchema):
    """No fields needed -- creates a new conversation for the authenticated user."""

    pass


class MessageSend(BaseSchema):
    """Schema for sending a message in a conversation."""

    content: str
    image_base64: str | None = None  # Optional base64 image for analysis
    image_media_type: str = "image/jpeg"
    # Evidence metadata from SDK signing
    image_hash: str | None = None
    image_signature: str | None = None
    image_timestamp: str | None = None
    image_latitude: float | None = None
    image_longitude: float | None = None
    device_id: str | None = None
    capture_method: str | None = None  # 'camera' or 'gallery'


class MessageResponse(BaseSchema):
    """Schema for a single message in a conversation."""

    id: int
    conversation_id: int
    direction: str  # "inbound" or "outbound"
    content: str | None
    message_type: str
    created_at: datetime | None = None


class ConversationResponse(BaseSchema):
    """Schema for a conversation with its messages."""

    id: int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[MessageResponse] = []


class ChatResponse(BaseSchema):
    """Response from the AI chatbot after processing a message."""

    message: MessageResponse
    tool_calls: list[dict] = []  # For transparency -- show what tools were used
    quick_replies: list[dict] = []  # Suggested reply buttons [{"label", "value"}]
