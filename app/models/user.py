"""User-related models: User, Level, Badge, UserBadge."""

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
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import BadgeRarity, UserRole, WalletType

if TYPE_CHECKING:
    from app.models.activity import Activity, StakingPosition, TokenTransaction
    from app.models.api_key import ApiKey
    from app.models.authority import AuthorityUser
    from app.models.conversation import Conversation
    from app.models.report import Report
    from app.models.wallet import CustodialWallet, WithdrawalRequest


class Level(Base):
    """User level/tier in the gamification system."""

    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tier: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    title_en: Mapped[str] = mapped_column(String(100), nullable=False)
    title_es: Mapped[str] = mapped_column(String(100), nullable=False)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_es: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    min_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    multa_bonus: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="level")


class Badge(Base):
    """Achievement badges that users can earn."""

    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_es: Mapped[str] = mapped_column(String(100), nullable=False)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_es: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    rarity: Mapped[BadgeRarity] = mapped_column(
        default=BadgeRarity.COMMON, nullable=False
    )
    multa_reward: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0.000000")
    )
    criteria: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_nft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nft_metadata_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    users: Mapped[list["UserBadge"]] = relationship("UserBadge", back_populates="badge")


class UserBadge(Base):
    """Association table between users and badges."""

    __tablename__ = "user_badges"
    __table_args__ = (
        UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    badge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("badges.id", ondelete="CASCADE"), nullable=False
    )
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )
    nft_mint_address: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="badges")
    badge: Mapped["Badge"] = relationship("Badge", back_populates="users")


class User(TimestampMixin, Base):
    """Main user model for citizens, authorities, and admins."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    phone_number: Mapped[Optional[str]] = mapped_column(
        String(20), unique=True, nullable=True, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True, nullable=True, index=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    wallet_address: Mapped[Optional[str]] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    wallet_type: Mapped[WalletType] = mapped_column(
        default=WalletType.CUSTODIAL, nullable=False
    )

    # Profile
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="es", nullable=False)

    # Gamification
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("levels.id", ondelete="SET NULL"), nullable=True
    )
    reputation_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("100.00"), nullable=False
    )

    # Abuse prevention counters (see app/services/verification.py and
    # app/services/report.py for where these are maintained). Used to
    # compute ``rejection_rate`` for the UI warning flag.
    total_reports_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    rejected_reports_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[UserRole] = mapped_column(default=UserRole.CITIZEN, nullable=False)

    # Timestamps
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    level: Mapped[Optional["Level"]] = relationship("Level", back_populates="users")
    reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="reporter",
        foreign_keys="Report.reporter_id",
    )
    verified_reports: Mapped[list["Report"]] = relationship(
        "Report",
        back_populates="verifier",
        foreign_keys="Report.verifier_id",
    )
    activities: Mapped[list["Activity"]] = relationship(
        "Activity", back_populates="user"
    )
    badges: Mapped[list["UserBadge"]] = relationship(
        "UserBadge", back_populates="user", cascade="all, delete-orphan"
    )
    token_transactions: Mapped[list["TokenTransaction"]] = relationship(
        "TokenTransaction", back_populates="user"
    )
    staking_positions: Mapped[list["StakingPosition"]] = relationship(
        "StakingPosition", back_populates="user"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user"
    )
    authority_memberships: Mapped[list["AuthorityUser"]] = relationship(
        "AuthorityUser", back_populates="user"
    )
    custodial_wallet: Mapped[Optional["CustodialWallet"]] = relationship(
        "CustodialWallet", back_populates="user", uselist=False
    )
    withdrawal_requests: Mapped[list["WithdrawalRequest"]] = relationship(
        "WithdrawalRequest", back_populates="user"
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def rejection_rate(self) -> float:
        """Ratio of reports this user has had rejected by authority.

        Uses ``rejected_reports_count / max(total_reports_count, 1)`` so
        brand-new users with zero submissions see a 0.0 rate rather than
        dividing by zero.
        """
        total = self.total_reports_count or 0
        rejected = self.rejected_reports_count or 0
        return rejected / max(total, 1)

    @property
    def rejection_rate_warning(self) -> bool:
        """Whether the user has crossed the abuse-warning threshold.

        We only flag users with enough history to be meaningful
        (``total_reports_count >= 10``) and a rejection rate above 30%.
        Consumed by the chatbot and report-creation responses.
        """
        if (self.total_reports_count or 0) < 10:
            return False
        return self.rejection_rate > 0.30

    def __repr__(self) -> str:
        return f"<User {self.id} ({self.email or self.phone_number or self.username})>"
