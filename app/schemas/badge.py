"""Badge schemas for the Multando API.

This module contains schemas for badges and user achievements.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import Field

from app.schemas.base import BaseSchema


class BadgeRarity(str, Enum):
    """Badge rarity levels."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


class BadgeBase(BaseSchema):
    """Base schema for badge data."""

    code: str = Field(description="Unique badge code identifier")
    name_en: str = Field(description="Badge name in English")
    name_es: str = Field(description="Badge name in Spanish")
    description_en: str = Field(description="Badge description in English")
    description_es: str = Field(description="Badge description in Spanish")
    icon_url: str | None = Field(default=None, description="URL to badge icon")
    rarity: BadgeRarity = Field(description="Badge rarity level")
    multa_reward: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="MULTA tokens rewarded for earning this badge",
    )
    is_nft: bool = Field(
        default=False, description="Whether this badge can be minted as NFT"
    )


class BadgeResponse(BadgeBase):
    """Schema for badge response."""

    id: int = Field(description="Badge unique identifier")


class UserBadgeResponse(BaseSchema):
    """Schema for a badge awarded to a user."""

    badge: BadgeResponse = Field(description="Badge details")
    awarded_at: datetime = Field(description="When the badge was awarded")
    nft_mint_address: str | None = Field(
        default=None, description="Solana NFT mint address if minted"
    )
