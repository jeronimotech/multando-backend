"""Base model with common fields and mixins."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.enums import (
    ActivityType,
    AuthorityRole,
    BadgeRarity,
    ConversationStatus,
    EvidenceType,
    InfractionCategory,
    InfractionSeverity,
    MessageDirection,
    MessageType,
    ReportSource,
    ReportStatus,
    SubscriptionTier,
    TokenTxType,
    TxStatus,
    UserRole,
    VehicleCategory,
    WalletStatus,
    WalletType,
    WithdrawalStatus,
)


def _enum_values(e: type[enum.Enum]) -> list[str]:
    return [x.value for x in e]


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    type_annotation_map = {
        UserRole: SAEnum(UserRole, values_callable=_enum_values),
        ReportStatus: SAEnum(ReportStatus, values_callable=_enum_values),
        ReportSource: SAEnum(ReportSource, values_callable=_enum_values),
        VehicleCategory: SAEnum(VehicleCategory, values_callable=_enum_values),
        EvidenceType: SAEnum(EvidenceType, values_callable=_enum_values),
        ActivityType: SAEnum(ActivityType, values_callable=_enum_values),
        BadgeRarity: SAEnum(BadgeRarity, values_callable=_enum_values),
        InfractionCategory: SAEnum(InfractionCategory, values_callable=_enum_values),
        InfractionSeverity: SAEnum(InfractionSeverity, values_callable=_enum_values),
        WalletType: SAEnum(WalletType, values_callable=_enum_values),
        WalletStatus: SAEnum(WalletStatus, values_callable=_enum_values),
        WithdrawalStatus: SAEnum(WithdrawalStatus, values_callable=_enum_values),
        TokenTxType: SAEnum(TokenTxType, values_callable=_enum_values),
        TxStatus: SAEnum(TxStatus, values_callable=_enum_values),
        ConversationStatus: SAEnum(ConversationStatus, values_callable=_enum_values),
        MessageDirection: SAEnum(MessageDirection, values_callable=_enum_values),
        MessageType: SAEnum(MessageType, values_callable=_enum_values),
        SubscriptionTier: SAEnum(SubscriptionTier, values_callable=_enum_values),
        AuthorityRole: SAEnum(AuthorityRole, values_callable=_enum_values),
    }


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
