"""Webhook schemas for authority event notification configuration."""

from datetime import datetime
from typing import Optional

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


ALLOWED_EVENTS = {"report.created", "report.verified", "report.rejected"}


class WebhookCreateRequest(BaseSchema):
    """Schema for creating a new webhook."""

    url: str = Field(
        min_length=10,
        max_length=500,
        description="HTTPS URL to POST webhook payloads to",
    )
    events: list[str] = Field(
        min_length=1,
        description="List of event types to subscribe to",
    )
    secret: Optional[str] = Field(
        default=None,
        max_length=255,
        description="HMAC secret for signature verification (auto-generated if omitted)",
    )

    @field_validator("url")
    @classmethod
    def validate_https_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        invalid = set(v) - ALLOWED_EVENTS
        if invalid:
            raise ValueError(
                f"Invalid event types: {', '.join(invalid)}. "
                f"Allowed: {', '.join(sorted(ALLOWED_EVENTS))}"
            )
        return v


class WebhookUpdateRequest(BaseSchema):
    """Schema for updating an existing webhook. All fields optional."""

    url: Optional[str] = Field(default=None, min_length=10, max_length=500)
    events: Optional[list[str]] = Field(default=None, min_length=1)
    is_active: Optional[bool] = Field(default=None)

    @field_validator("url")
    @classmethod
    def validate_https_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None:
            invalid = set(v) - ALLOWED_EVENTS
            if invalid:
                raise ValueError(
                    f"Invalid event types: {', '.join(invalid)}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_EVENTS))}"
                )
        return v


class WebhookResponse(BaseSchema):
    """Schema for webhook response (list/detail views)."""

    id: int
    url: str
    events: list[str]
    is_active: bool
    last_triggered_at: Optional[datetime] = None
    last_status_code: Optional[int] = None
    failure_count: int = 0
    created_at: datetime


class WebhookCreatedResponse(BaseSchema):
    """Schema returned on webhook creation — includes the secret (shown once)."""

    id: int
    url: str
    events: list[str]
    is_active: bool
    secret: str = Field(description="HMAC signing secret (shown only once)")
    created_at: datetime


class WebhookListResponse(BaseSchema):
    """Paginated list of webhooks."""

    items: list[WebhookResponse]
    total: int


class WebhookTestResponse(BaseSchema):
    """Response after sending a test ping to a webhook URL."""

    success: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error: Optional[str] = None
