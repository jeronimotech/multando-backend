"""Level schemas for the Multando API.

This module contains schemas for user levels and tiers.
"""

from decimal import Decimal

from pydantic import Field

from app.schemas.base import BaseSchema


class LevelBase(BaseSchema):
    """Base schema for level data."""

    tier: int = Field(ge=1, description="Level tier number")
    title_en: str = Field(description="Level title in English")
    title_es: str = Field(description="Level title in Spanish")
    min_points: int = Field(ge=0, description="Minimum points required for this level")
    icon_url: str | None = Field(default=None, description="URL to level icon")
    multa_bonus: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="Bonus multiplier for MULTA rewards at this level",
    )


class LevelResponse(LevelBase):
    """Schema for level response."""

    id: int = Field(description="Level unique identifier")


class LevelList(BaseSchema):
    """Schema for list of levels."""

    items: list[LevelResponse] = Field(description="List of levels")
