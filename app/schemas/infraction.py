"""Infraction schemas for the Multando API.

This module contains schemas for traffic infractions and violations.
"""

from decimal import Decimal
from enum import Enum

from pydantic import Field

from app.schemas.base import BaseSchema


class InfractionCategory(str, Enum):
    """Infraction category types."""

    SPEED = "speed"
    SAFETY = "safety"
    PARKING = "parking"
    BEHAVIOR = "behavior"


class InfractionSeverity(str, Enum):
    """Infraction severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InfractionBase(BaseSchema):
    """Base schema for infraction data."""

    code: str = Field(description="Unique infraction code")
    name_en: str = Field(description="Infraction name in English")
    name_es: str = Field(description="Infraction name in Spanish")
    description_en: str = Field(description="Infraction description in English")
    description_es: str = Field(description="Infraction description in Spanish")
    category: InfractionCategory = Field(description="Infraction category")
    severity: InfractionSeverity = Field(description="Infraction severity level")
    points_reward: int = Field(
        default=0, ge=0, description="Points awarded for reporting this infraction"
    )
    multa_reward: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="MULTA tokens awarded for reporting this infraction",
    )
    icon: str | None = Field(default=None, description="Icon identifier or URL")


class InfractionResponse(InfractionBase):
    """Schema for infraction response."""

    id: int = Field(description="Infraction unique identifier")


class InfractionList(BaseSchema):
    """Schema for list of infractions."""

    items: list[InfractionResponse] = Field(description="List of infractions")
