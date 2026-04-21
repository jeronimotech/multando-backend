"""SQLAlchemy models package.

This module contains all database models for the Multando application.
"""

# Base and mixins
from app.models.base import Base, TimestampMixin

# Enumerations
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
    OfferType,
    PartnerCategory,
    PartnerStatus,
    PartnerTier,
    RedemptionStatus,
    ReportSource,
    ReportStatus,
    SubscriptionTier,
    TokenTxType,
    TxStatus,
    UserRole,
    VehicleCategory,
)

# User models
from app.models.user import Badge, Level, User, UserBadge

# Report models
from app.models.report import Evidence, Infraction, Report, VehicleType

# Activity models
from app.models.activity import Activity, StakingPosition, TokenTransaction

# Conversation models
from app.models.conversation import Conversation, Message

# City models
from app.models.city import City

# Authority models
from app.models.authority import Authority, AuthorityUser

# Webhook models
from app.models.webhook import AuthorityWebhook

# Wallet models
from app.models.wallet import CustodialWallet, HotWalletLedger, WithdrawalRequest

# API Key models
from app.models.api_key import ApiKey

# Partner models
from app.models.partner import OfferRedemption, Partner, PartnerOffer

# RECORD submission tracking
from app.models.record_submission import RecordSubmission, RecordSubmissionStatus

# Federation models
from app.models.federation import FederatedReport, FederationInstance

# OAuth models
from app.models.oauth import OAuthAuthorizationCode

__all__ = [
    # Base
    "Base",
    "TimestampMixin",
    # Enums
    "UserRole",
    "ReportStatus",
    "ReportSource",
    "VehicleCategory",
    "EvidenceType",
    "ActivityType",
    "BadgeRarity",
    "InfractionCategory",
    "InfractionSeverity",
    "TokenTxType",
    "TxStatus",
    "ConversationStatus",
    "MessageDirection",
    "MessageType",
    "SubscriptionTier",
    "AuthorityRole",
    "PartnerStatus",
    "PartnerTier",
    "PartnerCategory",
    "OfferType",
    "RedemptionStatus",
    # User models
    "User",
    "Level",
    "Badge",
    "UserBadge",
    # Report models
    "Report",
    "Evidence",
    "Infraction",
    "VehicleType",
    # Activity models
    "Activity",
    "TokenTransaction",
    "StakingPosition",
    # Conversation models
    "Conversation",
    "Message",
    # City models
    "City",
    # Authority models
    "Authority",
    "AuthorityUser",
    # Webhook models
    "AuthorityWebhook",
    # Wallet models
    "CustodialWallet",
    "WithdrawalRequest",
    "HotWalletLedger",
    # Partner models
    "Partner",
    "PartnerOffer",
    "OfferRedemption",
    # API Key models
    "ApiKey",
    # RECORD submission tracking
    "RecordSubmission",
    "RecordSubmissionStatus",
    # Federation models
    "FederatedReport",
    "FederationInstance",
    # OAuth models
    "OAuthAuthorizationCode",
]
