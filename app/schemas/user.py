"""User schemas for the Multando API.

This module contains schemas for user profiles and management.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.schemas.badge import UserBadgeResponse
from app.schemas.base import BaseSchema
from app.schemas.level import LevelResponse


class UserRole(str, Enum):
    """User role types."""

    USER = "user"
    VERIFIER = "verifier"
    MODERATOR = "moderator"
    ADMIN = "admin"


class UserBase(BaseSchema):
    """Base schema for user data."""

    email: EmailStr = Field(description="User's email address")
    username: str = Field(
        min_length=3, max_length=30, description="Unique username"
    )
    display_name: str = Field(
        min_length=1, max_length=100, description="Display name"
    )
    phone_number: str | None = Field(default=None, description="Phone number")
    locale: str = Field(default="en", description="Preferred locale")
    avatar_url: str | None = Field(default=None, description="Avatar image URL")


class UserCreate(UserBase):
    """Schema for creating a new user."""

    password: str = Field(min_length=8, description="User's password")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password contains at least one letter and one number."""
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username contains only allowed characters."""
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Username can only contain letters, numbers, and underscores"
            )
        return v.lower()


class UserUpdate(BaseSchema):
    """Schema for updating user data. All fields are optional."""

    email: EmailStr | None = Field(default=None, description="User's email address")
    username: str | None = Field(
        default=None, min_length=3, max_length=30, description="Unique username"
    )
    display_name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Display name"
    )
    phone_number: str | None = Field(default=None, description="Phone number")
    locale: str | None = Field(default=None, description="Preferred locale")
    avatar_url: str | None = Field(default=None, description="Avatar image URL")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        """Validate username contains only allowed characters."""
        if v is None:
            return v
        if not re.match(r"^[a-zA-Z0-9_]+$", v):
            raise ValueError(
                "Username can only contain letters, numbers, and underscores"
            )
        return v.lower()

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, v: str | None) -> str | None:
        """Validate locale is supported."""
        if v is None:
            return v
        supported_locales = ["en", "es"]
        if v not in supported_locales:
            raise ValueError(f"Locale must be one of: {', '.join(supported_locales)}")
        return v


class UserPublic(BaseSchema):
    """Public user profile schema visible to other users."""

    id: UUID = Field(description="User unique identifier")
    username: str = Field(description="Username")
    display_name: str = Field(description="Display name")
    avatar_url: str | None = Field(default=None, description="Avatar image URL")
    points: int = Field(default=0, ge=0, description="Total points earned")
    level: LevelResponse | None = Field(default=None, description="Current level")
    badges: list[UserBadgeResponse] = Field(
        default_factory=list, description="Badges earned"
    )
    created_at: datetime = Field(description="Account creation date")


class UserProfile(UserPublic):
    """Full user profile schema for the authenticated user."""

    email: EmailStr = Field(description="User's email address")
    phone_number: str | None = Field(default=None, description="Phone number")
    wallet_address: str | None = Field(
        default=None, description="Linked Solana wallet address"
    )
    reputation_score: Decimal = Field(
        default=Decimal("0"), description="Reputation score"
    )
    is_verified: bool = Field(default=False, description="Email verification status")
    role: UserRole = Field(default=UserRole.USER, description="User role")


class UserInDB(UserProfile):
    """User schema with database fields including password hash."""

    password_hash: str = Field(description="Hashed password")
    updated_at: datetime | None = Field(
        default=None, description="Last update timestamp"
    )


# Backward compatibility alias
UserSummary = UserPublic
