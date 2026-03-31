"""Custodial wallet models for managed wallet infrastructure."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import WalletStatus, WithdrawalStatus

if TYPE_CHECKING:
    from app.models.user import User


class CustodialWallet(TimestampMixin, Base):
    """Custodial wallet with encrypted private key for a user.

    The private key is encrypted using envelope encryption:
    - DEK (AES-256-GCM) encrypts the private key
    - KEK (KMS/Fernet) encrypts the DEK
    """

    __tablename__ = "custodial_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    public_key: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    encrypted_private_key: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    encrypted_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    iv: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
    status: Mapped[WalletStatus] = mapped_column(
        default=WalletStatus.ACTIVE, nullable=False
    )
    last_tx_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="custodial_wallet")


class WithdrawalRequest(TimestampMixin, Base):
    """Withdrawal request from custodial wallet to external address."""

    __tablename__ = "withdrawal_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    destination_address: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        default=WithdrawalStatus.PENDING, nullable=False, index=True
    )
    tx_signature: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True
    )
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    verification_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )
    verification_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="withdrawal_requests")


class HotWalletLedger(Base):
    """Internal ledger tracking user token allocations within the hot wallet pool.

    This is the off-chain accounting for custodial users. Their tokens
    are pooled in the platform hot wallet, and this ledger tracks each
    user's share.
    """

    __tablename__ = "hot_wallet_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
