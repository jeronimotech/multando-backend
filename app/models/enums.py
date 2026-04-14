"""Enumeration types for all models."""

from enum import Enum


class UserRole(str, Enum):
    """User roles in the system."""

    CITIZEN = "citizen"
    AUTHORITY = "authority"
    ADMIN = "admin"


class ReportStatus(str, Enum):
    """Status of a traffic violation report.

    Workflow:
        pending -> community_verified (community threshold reached)
                -> authority_review (after 2 days stale)
        community_verified / authority_review -> approved (authority validated)
                                              -> rejected (authority rejected)

    Notes:
        ``verified`` is kept for backward compatibility with legacy records
        but is no longer set by new flows. ``disputed`` is also legacy.
    """

    PENDING = "pending"
    COMMUNITY_VERIFIED = "community_verified"
    AUTHORITY_REVIEW = "authority_review"
    APPROVED = "approved"
    VERIFIED = "verified"  # legacy / backward-compat
    REJECTED = "rejected"
    DISPUTED = "disputed"


class ReportSource(str, Enum):
    """Source platform where the report was submitted."""

    WEB = "web"
    MOBILE = "mobile"
    WHATSAPP = "whatsapp"
    SDK = "sdk"


class VehicleCategory(str, Enum):
    """Category of vehicle involved in the report."""

    PRIVATE = "private"
    PUBLIC = "public"
    DIPLOMATIC = "diplomatic"
    EMERGENCY = "emergency"
    COMMERCIAL = "commercial"


class EvidenceType(str, Enum):
    """Type of evidence attached to a report."""

    IMAGE = "image"
    VIDEO = "video"


class ActivityType(str, Enum):
    """Types of activities that can earn points or rewards."""

    REPORT_SUBMITTED = "report_submitted"
    REPORT_VERIFIED = "report_verified"
    VERIFICATION_DONE = "verification_done"
    DAILY_LOGIN = "daily_login"
    REFERRAL = "referral"
    LEVEL_UP = "level_up"
    BADGE_EARNED = "badge_earned"
    FALSE_REPORT_PENALTY = "false_report_penalty"


class BadgeRarity(str, Enum):
    """Rarity level of badges."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class InfractionCategory(str, Enum):
    """Category of traffic infraction."""

    SPEED = "speed"
    SAFETY = "safety"
    PARKING = "parking"
    BEHAVIOR = "behavior"


class InfractionSeverity(str, Enum):
    """Severity level of traffic infraction."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WalletType(str, Enum):
    """Type of wallet associated with user."""

    CUSTODIAL = "custodial"
    SELF_CUSTODIAL = "self_custodial"


class WalletStatus(str, Enum):
    """Status of a custodial wallet."""

    ACTIVE = "active"
    FROZEN = "frozen"
    DEACTIVATED = "deactivated"


class WithdrawalStatus(str, Enum):
    """Status of a withdrawal request."""

    PENDING_VERIFICATION = "pending_verification"
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TokenTxType(str, Enum):
    """Type of token transaction."""

    REWARD = "reward"
    STAKE = "stake"
    UNSTAKE = "unstake"
    TRANSFER = "transfer"
    BURN = "burn"
    WITHDRAWAL = "withdrawal"


class TxStatus(str, Enum):
    """Status of a blockchain transaction."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class ConversationStatus(str, Enum):
    """Status of a WhatsApp conversation."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class MessageDirection(str, Enum):
    """Direction of a message in a conversation."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(str, Enum):
    """Type of WhatsApp message."""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LOCATION = "location"
    BUTTON = "button"
    LIST = "list"


class SubscriptionTier(str, Enum):
    """Subscription tier for authorities."""

    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class AuthorityRole(str, Enum):
    """Role of a user within an authority organization."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"
