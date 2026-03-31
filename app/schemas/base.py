"""Base schemas for the Multando API.

This module contains common base schemas that other schemas inherit from.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Base schema with common configuration for all schemas."""

    model_config = ConfigDict(from_attributes=True)


class TimestampSchema(BaseSchema):
    """Schema mixin for models with timestamp fields."""

    created_at: datetime
    updated_at: datetime | None = None


class UUIDSchema(BaseSchema):
    """Schema mixin for models with UUID primary key."""

    id: UUID
