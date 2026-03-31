"""Activity schemas for the Multando API.

This module contains schemas for user activity and rewards tracking.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class ActivityType(str, Enum):
    """Activity type categories."""

    REPORT_SUBMITTED = "report_submitted"
    REPORT_VERIFIED = "report_verified"
    REPORT_REJECTED = "report_rejected"
    VERIFICATION_DONE = "verification_done"
    BADGE_EARNED = "badge_earned"
    LEVEL_UP = "level_up"
    DAILY_LOGIN = "daily_login"
    STREAK_BONUS = "streak_bonus"
    REFERRAL_BONUS = "referral_bonus"
    STAKING_REWARD = "staking_reward"
    NFT_MINTED = "nft_minted"


class ReferenceType(str, Enum):
    """Reference type for activity metadata."""

    REPORT = "report"
    BADGE = "badge"
    LEVEL = "level"
    USER = "user"
    TRANSACTION = "transaction"
    NFT = "nft"


class ActivityBase(BaseSchema):
    """Base schema for activity data."""

    type: ActivityType = Field(description="Type of activity")
    points_earned: int = Field(default=0, ge=0, description="Points earned from activity")
    multa_earned: Decimal = Field(
        default=Decimal("0"), ge=0, description="MULTA tokens earned from activity"
    )
    reference_type: ReferenceType | None = Field(
        default=None, description="Type of referenced entity"
    )
    reference_id: UUID | None = Field(
        default=None, description="ID of referenced entity"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional activity metadata"
    )


class ActivityResponse(ActivityBase):
    """Schema for activity response."""

    id: UUID = Field(description="Activity unique identifier")
    created_at: datetime = Field(description="When the activity occurred")


class ActivityList(BaseSchema):
    """Schema for paginated list of activities."""

    items: list[ActivityResponse] = Field(description="List of activities")
    total: int = Field(description="Total number of activities")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")


class ActivitySummary(BaseSchema):
    """Schema for activity summary statistics."""

    total_points_earned: int = Field(description="Total points earned")
    total_multa_earned: Decimal = Field(description="Total MULTA tokens earned")
    activities_count: int = Field(description="Total number of activities")
    period_start: datetime = Field(description="Start of the summary period")
    period_end: datetime = Field(description="End of the summary period")
