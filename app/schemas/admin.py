"""Admin and authority management schemas for the Multando API.

This module contains schemas for super admin and authority admin endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AuthorityRole, SubscriptionTier
from app.schemas.base import BaseSchema
from app.schemas.city import CityResponse


# ---------------------------------------------------------------------------
# Authority CRUD (Super Admin)
# ---------------------------------------------------------------------------


class AuthorityCreateRequest(BaseSchema):
    """Schema for creating a new authority via admin panel."""

    name: str = Field(min_length=2, max_length=200, description="Authority name")
    code: str = Field(min_length=2, max_length=50, description="Unique authority code")
    city_id: int = Field(description="ID of the city this authority belongs to")
    country: str = Field(
        min_length=2, max_length=2, default="DO", description="ISO 3166-1 alpha-2 country code"
    )
    contact_email: EmailStr | None = Field(default=None, description="Contact email address")
    contact_name: str | None = Field(default=None, max_length=200, description="Contact person name")
    subscription_tier: SubscriptionTier = Field(
        default=SubscriptionTier.FREE, description="Subscription tier"
    )


class AuthorityUpdateRequest(BaseSchema):
    """Schema for updating an authority. All fields optional."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    city_id: int | None = Field(default=None)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    contact_email: EmailStr | None = Field(default=None)
    contact_name: str | None = Field(default=None, max_length=200)
    subscription_tier: SubscriptionTier | None = Field(default=None)
    rate_limit: int | None = Field(default=None, ge=0)


class StaffMemberResponse(BaseSchema):
    """Schema for a staff member within an authority."""

    user_id: UUID = Field(description="User ID")
    email: str | None = Field(default=None, description="User email")
    display_name: str | None = Field(default=None, description="Display name")
    role: AuthorityRole = Field(description="Role within the authority")
    joined_at: datetime = Field(description="When the user joined the authority")


class AuthorityDetailResponse(BaseSchema):
    """Full authority detail including staff and city."""

    id: int
    name: str
    code: str
    country: str
    city: str | None = None
    city_id: int | None = None
    city_info: CityResponse | None = None
    subscription_tier: SubscriptionTier
    subscription_expires_at: datetime | None = None
    rate_limit: int
    contact_email: str | None = None
    contact_name: str | None = None
    created_at: datetime
    staff: list[StaffMemberResponse] = Field(default_factory=list)


class AuthorityListItem(BaseSchema):
    """Condensed authority info for list views."""

    id: int
    name: str
    code: str
    country: str
    city: str | None = None
    city_id: int | None = None
    subscription_tier: SubscriptionTier
    contact_email: str | None = None
    staff_count: int = 0
    created_at: datetime


class AuthorityListResponse(BaseSchema):
    """Paginated list of authorities."""

    items: list[AuthorityListItem]
    total: int
    page: int
    page_size: int


class AuthorityCreatedAdminResponse(BaseSchema):
    """Response after creating an authority (includes one-time API key)."""

    authority: AuthorityDetailResponse
    api_key: str = Field(description="API key shown only once -- save it securely")


# ---------------------------------------------------------------------------
# Staff management
# ---------------------------------------------------------------------------


class AddStaffRequest(BaseSchema):
    """Schema for adding a staff member to an authority."""

    email: EmailStr = Field(description="Email of the user to add")
    role: AuthorityRole = Field(
        default=AuthorityRole.VIEWER, description="Role within the authority"
    )


class UpdateStaffRoleRequest(BaseSchema):
    """Schema for updating a staff member's role."""

    role: AuthorityRole = Field(description="New role within the authority")


# ---------------------------------------------------------------------------
# City management (Super Admin)
# ---------------------------------------------------------------------------


class CityCreateRequest(BaseSchema):
    """Schema for creating a city."""

    name: str = Field(min_length=1, max_length=100, description="City name")
    country_code: str = Field(min_length=2, max_length=2, description="ISO country code")
    state_province: str | None = Field(default=None, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = Field(default="UTC", max_length=50)


class CityUpdateRequest(BaseSchema):
    """Schema for updating a city. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    state_province: str | None = Field(default=None, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str | None = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# Dashboard / Stats
# ---------------------------------------------------------------------------


class PlatformStatsResponse(BaseSchema):
    """Platform-wide statistics for the super admin dashboard."""

    total_users: int
    total_reports: int
    total_authorities: int
    total_cities: int
    reports_today: int
    reports_this_month: int


class AuthorityDashboardResponse(BaseSchema):
    """Authority-scoped dashboard statistics."""

    total_reports: int
    reports_by_status: dict[str, int] = Field(default_factory=dict)
    recent_reports: list[dict] = Field(default_factory=list)
    top_infractions: list[dict] = Field(default_factory=list)
    verification_rate: float = Field(
        default=0.0, description="Percentage of reports that have been verified"
    )
