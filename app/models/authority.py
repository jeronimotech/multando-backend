"""Authority-related models: Authority, AuthorityUser."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import AuthorityRole, SubscriptionTier

if TYPE_CHECKING:
    from app.models.city import City
    from app.models.user import User


class Authority(Base):
    """Government or regulatory authority organization."""

    __tablename__ = "authorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="DO")
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Subscription
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        default=SubscriptionTier.FREE, nullable=False
    )
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # API access
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    rate_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    # Contact
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    # Relationships
    city_rel: Mapped[Optional["City"]] = relationship(
        "City", back_populates="authorities"
    )
    users: Mapped[list["AuthorityUser"]] = relationship(
        "AuthorityUser", back_populates="authority", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Authority {self.code} ({self.name})>"


class AuthorityUser(Base):
    """Association between users and authorities with role."""

    __tablename__ = "authority_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    authority_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("authorities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[AuthorityRole] = mapped_column(
        default=AuthorityRole.VIEWER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    # Relationships
    authority: Mapped["Authority"] = relationship("Authority", back_populates="users")
    user: Mapped["User"] = relationship("User", back_populates="authority_memberships")

    def __repr__(self) -> str:
        return f"<AuthorityUser {self.id} (authority: {self.authority_id}, user: {self.user_id}, role: {self.role.value})>"
