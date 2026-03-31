"""Activity-related models: Activity, TokenTransaction, StakingPosition."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import ActivityType, TokenTxType, TxStatus

if TYPE_CHECKING:
    from app.models.user import User


class Activity(Base):
    """User activity log for gamification events."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[ActivityType] = mapped_column(nullable=False, index=True)
    points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    multa_earned: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0.000000"), nullable=False
    )
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    activity_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False, index=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="activities")
    token_transactions: Mapped[list["TokenTransaction"]] = relationship(
        "TokenTransaction", back_populates="activity"
    )

    def __repr__(self) -> str:
        return f"<Activity {self.id} ({self.type.value})>"


class TokenTransaction(Base):
    """Blockchain token transaction record."""

    __tablename__ = "token_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[TokenTxType] = mapped_column(nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    tx_signature: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    status: Mapped[TxStatus] = mapped_column(
        default=TxStatus.PENDING, nullable=False, index=True
    )
    activity_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="token_transactions")
    activity: Mapped[Optional["Activity"]] = relationship(
        "Activity", back_populates="token_transactions"
    )

    def __repr__(self) -> str:
        return f"<TokenTransaction {self.id} ({self.type.value}: {self.amount})>"


class StakingPosition(Base):
    """User staking position for MULTA tokens."""

    __tablename__ = "staking_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    staked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    unlock_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rewards_claimed: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0.000000"), nullable=False
    )
    last_claim_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="staking_positions")

    def __repr__(self) -> str:
        return f"<StakingPosition {self.id} (amount: {self.amount}, active: {self.is_active})>"
