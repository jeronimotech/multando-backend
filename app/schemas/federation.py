"""Federation schemas for cross-instance data sharing."""

from datetime import datetime

from pydantic import Field

from app.schemas.base import BaseSchema


class FederatedReportItem(BaseSchema):
    """Single anonymized report summary sent from an instance."""

    short_id: str = Field(max_length=20)
    infraction_code: str | None = Field(default=None, max_length=50)
    infraction_name: str | None = Field(default=None, max_length=200)
    vehicle_category: str | None = Field(default=None, max_length=50)
    city_name: str | None = Field(default=None, max_length=200)
    status: str = Field(max_length=20)
    reported_at: datetime
    latitude_approx: float | None = Field(default=None)
    longitude_approx: float | None = Field(default=None)


class FederationSyncRequest(BaseSchema):
    """Payload sent by a self-hosted instance to sync reports."""

    instance_id: str = Field(max_length=50)
    items: list[FederatedReportItem]


class FederationSyncResponse(BaseSchema):
    """Response returned after a successful sync."""

    received_count: int
    instance_id: str


class FederationCityBreakdown(BaseSchema):
    """Report count breakdown by city."""

    city_name: str
    count: int


class FederationStatsResponse(BaseSchema):
    """Aggregated federation statistics."""

    total_instances: int
    total_federated_reports: int
    by_city: list[FederationCityBreakdown]


class FederationInstanceRegister(BaseSchema):
    """Schema for registering a new federation instance."""

    name: str = Field(max_length=200)
    city: str | None = Field(default=None, max_length=200)
    country: str = Field(default="CO", max_length=5)


class FederationInstanceResponse(BaseSchema):
    """Response after registering an instance (API key shown once)."""

    instance_id: str
    api_key: str
    name: str


class FederationInstanceListItem(BaseSchema):
    """Instance summary for admin listing."""

    instance_id: str
    name: str
    city: str | None
    country: str
    is_active: bool
    last_sync_at: datetime | None
    total_reports_synced: int
    registered_at: datetime | None
