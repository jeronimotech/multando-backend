"""Authority schemas for the Multando B2B API.

This module contains schemas for authority (government/regulatory body) endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import SubscriptionTier


class AuthorityCreate(BaseModel):
    """Schema for creating a new authority."""

    name: str = Field(min_length=2, max_length=200, description="Authority name")
    code: str = Field(min_length=2, max_length=20, description="Unique authority code")
    country: str = Field(
        min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code"
    )
    city: Optional[str] = Field(default=None, description="City name (optional)")
    contact_email: EmailStr = Field(description="Contact email address")
    contact_name: str = Field(description="Contact person name")


class AuthorityResponse(BaseModel):
    """Schema for authority response."""

    id: int = Field(description="Authority ID")
    name: str = Field(description="Authority name")
    code: str = Field(description="Unique authority code")
    country: str = Field(description="ISO 3166-1 alpha-2 country code")
    city: Optional[str] = Field(default=None, description="City name")
    subscription_tier: SubscriptionTier = Field(description="Current subscription tier")
    subscription_expires_at: Optional[datetime] = Field(
        default=None, description="Subscription expiration date"
    )
    rate_limit: int = Field(description="API rate limit (requests per day)")
    contact_email: Optional[str] = Field(
        default=None, description="Contact email address"
    )
    contact_name: Optional[str] = Field(default=None, description="Contact person name")
    created_at: datetime = Field(description="When the authority was created")

    class Config:
        """Pydantic configuration."""

        from_attributes = True


class AuthorityCreatedResponse(BaseModel):
    """Schema for authority creation response (includes API key)."""

    authority: AuthorityResponse = Field(description="Created authority details")
    api_key: str = Field(
        description="API key for authentication (shown only once, save it securely)"
    )


class AuthorityReportFilters(BaseModel):
    """Schema for filtering authority reports."""

    status: Optional[str] = Field(default=None, description="Filter by report status")
    from_date: Optional[datetime] = Field(
        default=None, description="Filter by start date"
    )
    to_date: Optional[datetime] = Field(default=None, description="Filter by end date")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(
        default=50, ge=1, le=100, description="Number of items per page"
    )


class AnalyticsResponse(BaseModel):
    """Schema for analytics response."""

    total_reports: int = Field(description="Total number of reports in jurisdiction")
    by_status: dict[str, int] = Field(description="Report counts by status")
    top_infractions: list[dict] = Field(description="Top 10 most reported infractions")
    daily_counts: list[dict] = Field(description="Daily report counts (last 30 days)")


class HeatmapPoint(BaseModel):
    """Schema for a single heatmap point."""

    lat: float = Field(description="Latitude coordinate")
    lng: float = Field(description="Longitude coordinate")
    status: str = Field(description="Report status")


class HeatmapResponse(BaseModel):
    """Schema for heatmap data response."""

    points: list[HeatmapPoint] = Field(description="List of heatmap points")
