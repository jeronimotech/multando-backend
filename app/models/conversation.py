"""Conversation-related models: Conversation, Message for WhatsApp bot."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import ConversationStatus, MessageDirection, MessageType

if TYPE_CHECKING:
    from app.models.user import User


class Conversation(TimestampMixin, Base):
    """WhatsApp conversation session with a user."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ConversationStatus] = mapped_column(
        default=ConversationStatus.ACTIVE, nullable=False, index=True
    )
    current_step: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    draft_report: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} ({self.phone_number}, {self.status.value})>"


class Message(Base):
    """Individual message in a WhatsApp conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    direction: Mapped[MessageDirection] = mapped_column(nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_type: Mapped[MessageType] = mapped_column(
        default=MessageType.TEXT, nullable=False
    )
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )
    message_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<Message {self.id} ({self.direction.value}: {self.message_type.value})>"
