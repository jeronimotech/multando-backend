"""Authority webhook model for real-time event notifications."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.authority import Authority


class AuthorityWebhook(TimestampMixin, Base):
    """Webhook configuration for authority event notifications.

    Authorities register HTTPS URLs to receive POST callbacks when
    relevant events occur (e.g. report.created, report.verified,
    report.rejected) within their city.
    """

    __tablename__ = "authority_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    authority_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("authorities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    events: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    authority: Mapped["Authority"] = relationship(
        "Authority", back_populates="webhooks"
    )

    def __repr__(self) -> str:
        return f"<AuthorityWebhook {self.id} (authority: {self.authority_id}, url: {self.url})>"
