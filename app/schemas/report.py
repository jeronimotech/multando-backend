"""Report schemas for the Multando API.

This module contains schemas for traffic violation reports.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.base import BaseSchema
from app.schemas.evidence import EvidenceResponse
from app.schemas.infraction import InfractionResponse
from app.schemas.user import UserPublic
from app.schemas.vehicle_type import VehicleTypeResponse


class ReportStatus(str, Enum):
    """Report status types."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    DISPUTED = "disputed"


class ReportSource(str, Enum):
    """Report source types."""

    WEB = "web"
    MOBILE = "mobile"
    WHATSAPP = "whatsapp"


class VehicleCategory(str, Enum):
    """Vehicle category types."""

    PRIVATE = "private"
    PUBLIC = "public"
    DIPLOMATIC = "diplomatic"
    EMERGENCY = "emergency"
    COMMERCIAL = "commercial"


class LocationSchema(BaseSchema):
    """Schema for location data."""

    lat: float = Field(ge=-90, le=90, description="Latitude coordinate")
    lon: float = Field(ge=-180, le=180, description="Longitude coordinate")
    address: str | None = Field(default=None, description="Street address")
    city: str | None = Field(default=None, description="City name")
    country: str | None = Field(default=None, description="Country name")


class ReportBase(BaseSchema):
    """Base schema for report data."""

    incident_datetime: datetime = Field(description="When the incident occurred")
    vehicle_plate: str | None = Field(
        default=None, description="Vehicle license plate number"
    )
    location: LocationSchema = Field(description="Location of the incident")


class ReportCreate(ReportBase):
    """Schema for creating a new report."""

    infraction_id: int = Field(description="ID of the infraction type")
    vehicle_type_id: int | None = Field(default=None, description="ID of the vehicle type")
    vehicle_category: VehicleCategory = Field(
        default=VehicleCategory.PRIVATE, description="Vehicle category"
    )
    source: ReportSource = Field(
        default=ReportSource.MOBILE, description="Source of the report"
    )

    @field_validator("vehicle_plate")
    @classmethod
    def validate_vehicle_plate(cls, v: str | None) -> str | None:
        """Normalize vehicle plate to uppercase."""
        if v is not None:
            return v.upper().strip()
        return v

    @field_validator("incident_datetime")
    @classmethod
    def validate_incident_datetime(cls, v: datetime) -> datetime:
        """Validate incident datetime is not in the future."""
        if v > datetime.now():
            raise ValueError("Incident datetime cannot be in the future")
        return v


class ReportUpdate(BaseSchema):
    """Schema for updating a report (for verifiers)."""

    status: ReportStatus = Field(description="New report status")
    rejection_reason: str | None = Field(
        default=None, description="Reason for rejection (required if rejecting)"
    )

    @model_validator(mode="after")
    def validate_rejection_reason(self) -> "ReportUpdate":
        """Validate rejection reason is provided when rejecting."""
        if self.status == ReportStatus.REJECTED and not self.rejection_reason:
            raise ValueError("Rejection reason is required when rejecting a report")
        return self


class ReportSummary(BaseSchema):
    """Schema for report summary in list views."""

    id: UUID = Field(description="Report unique identifier")
    short_id: str = Field(description="Human-readable short ID")
    status: ReportStatus = Field(description="Current report status")
    vehicle_plate: str | None = Field(default=None, description="Vehicle license plate")
    vehicle_type: VehicleTypeResponse | None = Field(
        default=None, description="Vehicle type"
    )
    infraction: InfractionResponse = Field(description="Infraction type")
    location: LocationSchema = Field(description="Location of the incident")
    created_at: datetime = Field(description="When the report was submitted")


class ReportDetail(ReportSummary):
    """Schema for detailed report view."""

    reporter: UserPublic = Field(description="User who submitted the report")
    verifier: UserPublic | None = Field(
        default=None, description="User who verified the report"
    )
    evidences: list[EvidenceResponse] = Field(
        default_factory=list, description="Evidence files"
    )
    verified_at: datetime | None = Field(
        default=None, description="When the report was verified"
    )
    on_chain: bool = Field(default=False, description="Whether report is on blockchain")
    tx_signature: str | None = Field(
        default=None, description="Blockchain transaction signature"
    )
    incident_datetime: datetime = Field(description="When the incident occurred")
    vehicle_category: VehicleCategory = Field(description="Vehicle category")
    source: ReportSource = Field(description="Source of the report")
    rejection_reason: str | None = Field(
        default=None, description="Reason if report was rejected"
    )


class ReportList(BaseSchema):
    """Schema for paginated list of reports."""

    items: list[ReportSummary] = Field(description="List of reports")
    total: int = Field(description="Total number of reports")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
