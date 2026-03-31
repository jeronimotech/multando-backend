"""Schemas for API key management endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseSchema


class ApiKeyCreateRequest(BaseSchema):
    """Request schema for creating a new API key."""

    name: str = Field(
        min_length=1,
        max_length=255,
        description="Developer-given name for the API key (e.g. 'My App Production')",
    )
    scopes: list[str] = Field(
        default=[
            "reports:create",
            "reports:read",
            "infractions:read",
            "users:read",
            "balance:read",
        ],
        description="Permission scopes for the key",
    )
    rate_limit: int = Field(
        default=60,
        ge=1,
        le=10000,
        description="Requests per minute",
    )
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Number of days until key expires (None = no expiry)",
    )
    environment: str = Field(
        default="production",
        pattern="^(sandbox|production)$",
        description="Environment: 'sandbox' (mult_test_) or 'production' (mult_live_)",
    )


class ApiKeyCreateResponse(BaseSchema):
    """Response returned when a new API key is created.

    IMPORTANT: The full `key` value is only returned ONCE at creation time.
    It cannot be retrieved again.
    """

    id: int
    key: str = Field(description="Full API key (shown only once)")
    key_prefix: str = Field(description="First 8 characters of the key for identification")
    name: str
    scopes: list[str]
    rate_limit: int
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApiKeyResponse(BaseSchema):
    """Response schema for an existing API key (full key NOT included)."""

    id: int
    key_prefix: str = Field(description="First 8 characters of the key for identification")
    name: str
    is_active: bool
    scopes: list[str]
    rate_limit: int
    last_used_at: Optional[datetime] = None
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApiKeyListResponse(BaseSchema):
    """Paginated list of API keys."""

    items: list[ApiKeyResponse]
    total: int
