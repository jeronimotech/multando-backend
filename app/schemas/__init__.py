"""Pydantic schemas package for the Multando API.

This module exports all Pydantic models (schemas) for request/response validation.
"""

# Base schemas
from app.schemas.base import BaseSchema, TimestampSchema, UUIDSchema

# Common response schemas
from app.schemas.common import (
    ErrorResponse,
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
)

# Authentication schemas
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    WalletLinkRequest,
)

# Level schemas
from app.schemas.level import LevelBase, LevelList, LevelResponse

# Badge schemas
from app.schemas.badge import (
    BadgeBase,
    BadgeRarity,
    BadgeResponse,
    UserBadgeResponse,
)

# User schemas
from app.schemas.user import (
    UserBase,
    UserCreate,
    UserInDB,
    UserProfile,
    UserPublic,
    UserRole,
    UserSummary,
    UserUpdate,
)

# Vehicle type schemas
from app.schemas.vehicle_type import (
    VehicleTypeBase,
    VehicleTypeList,
    VehicleTypeResponse,
)

# Infraction schemas
from app.schemas.infraction import (
    InfractionBase,
    InfractionCategory,
    InfractionList,
    InfractionResponse,
    InfractionSeverity,
)

# Evidence schemas
from app.schemas.evidence import (
    EvidenceBase,
    EvidenceCreate,
    EvidenceResponse,
    EvidenceType,
    EvidenceUploadResponse,
)

# Report schemas
from app.schemas.report import (
    LocationSchema,
    ReportBase,
    ReportCreate,
    ReportDetail,
    ReportList,
    ReportSource,
    ReportStatus,
    ReportSummary,
    ReportUpdate,
    VehicleCategory,
)

# Activity schemas
from app.schemas.activity import (
    ActivityBase,
    ActivityList,
    ActivityResponse,
    ActivitySummary,
    ActivityType,
    ReferenceType,
)

# Gamification schemas
from app.schemas.gamification import (
    AchievementProgress,
    LeaderboardEntry,
    LeaderboardPeriod,
    LeaderboardResponse,
    UserAchievementsResponse,
    UserStatsResponse,
)

# Blockchain schemas
from app.schemas.blockchain import (
    ClaimRewardsResponse,
    NFTMintRequest,
    NFTMintResponse,
    StakeRequest,
    StakingInfoResponse,
    TokenBalanceResponse,
    TokenTransactionBase,
    TokenTransactionList,
    TokenTransactionResponse,
    UnstakeRequest,
    UserStakingInfoResponse,
)

# Re-export blockchain enums from models for convenience
from app.models.enums import TokenTxType, TxStatus


# Health check schema (backward compatibility)
from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Health check response schema."""

    status: str
    version: str


__all__ = [
    # Base
    "BaseSchema",
    "TimestampSchema",
    "UUIDSchema",
    # Common
    "MessageResponse",
    "ErrorResponse",
    "PaginationParams",
    "PaginatedResponse",
    # Auth
    "RegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "RefreshRequest",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "WalletLinkRequest",
    # Level
    "LevelBase",
    "LevelResponse",
    "LevelList",
    # Badge
    "BadgeRarity",
    "BadgeBase",
    "BadgeResponse",
    "UserBadgeResponse",
    # User
    "UserRole",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserPublic",
    "UserProfile",
    "UserInDB",
    "UserSummary",
    # Vehicle Type
    "VehicleTypeBase",
    "VehicleTypeResponse",
    "VehicleTypeList",
    # Infraction
    "InfractionCategory",
    "InfractionSeverity",
    "InfractionBase",
    "InfractionResponse",
    "InfractionList",
    # Evidence
    "EvidenceType",
    "EvidenceBase",
    "EvidenceCreate",
    "EvidenceResponse",
    "EvidenceUploadResponse",
    # Report
    "ReportStatus",
    "ReportSource",
    "VehicleCategory",
    "LocationSchema",
    "ReportBase",
    "ReportCreate",
    "ReportUpdate",
    "ReportSummary",
    "ReportDetail",
    "ReportList",
    # Activity
    "ActivityType",
    "ReferenceType",
    "ActivityBase",
    "ActivityResponse",
    "ActivityList",
    "ActivitySummary",
    # Gamification
    "LeaderboardPeriod",
    "LeaderboardEntry",
    "LeaderboardResponse",
    "UserStatsResponse",
    "AchievementProgress",
    "UserAchievementsResponse",
    # Blockchain
    "TokenTxType",
    "TxStatus",
    "TokenBalanceResponse",
    "TokenTransactionBase",
    "TokenTransactionResponse",
    "TokenTransactionList",
    "StakeRequest",
    "UnstakeRequest",
    "ClaimRewardsResponse",
    "StakingInfoResponse",
    "NFTMintRequest",
    "NFTMintResponse",
    # Health
    "HealthCheck",
]
