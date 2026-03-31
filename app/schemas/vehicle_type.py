"""Vehicle type schemas for the Multando API.

This module contains schemas for vehicle types and categories.
"""

from pydantic import Field

from app.schemas.base import BaseSchema


class VehicleTypeBase(BaseSchema):
    """Base schema for vehicle type data."""

    code: str = Field(description="Unique vehicle type code")
    name_en: str = Field(description="Vehicle type name in English")
    name_es: str = Field(description="Vehicle type name in Spanish")
    icon: str | None = Field(default=None, description="Icon identifier or URL")
    plate_pattern: str | None = Field(
        default=None, description="Regex pattern for license plate validation"
    )
    requires_plate: bool = Field(
        default=True, description="Whether this vehicle type requires a license plate"
    )


class VehicleTypeResponse(VehicleTypeBase):
    """Schema for vehicle type response."""

    id: int = Field(description="Vehicle type unique identifier")


class VehicleTypeList(BaseSchema):
    """Schema for list of vehicle types."""

    items: list[VehicleTypeResponse] = Field(description="List of vehicle types")
