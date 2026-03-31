"""Authentication schemas for the Multando API.

This module contains schemas for user authentication, registration, and wallet linking.
"""

import re

from pydantic import EmailStr, Field, field_validator

from app.schemas.base import BaseSchema


class RegisterRequest(BaseSchema):
    """Schema for user registration request."""

    email: EmailStr = Field(description="User's email address")
    password: str = Field(min_length=8, description="User's password")
    username: str = Field(
        min_length=3, max_length=30, description="Unique username"
    )
    display_name: str = Field(
        min_length=1, max_length=100, description="Display name"
    )
    phone_number: str | None = Field(
        default=None, description="Optional phone number"
    )
    locale: str = Field(default="en", description="User's preferred locale")

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

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, v: str) -> str:
        """Validate locale is supported."""
        supported_locales = ["en", "es"]
        if v not in supported_locales:
            raise ValueError(f"Locale must be one of: {', '.join(supported_locales)}")
        return v


class LoginRequest(BaseSchema):
    """Schema for user login request."""

    email: EmailStr = Field(description="User's email address")
    password: str = Field(description="User's password")


class TokenResponse(BaseSchema):
    """Schema for authentication token response."""

    access_token: str = Field(description="JWT access token")
    refresh_token: str = Field(description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(description="Access token expiration time in seconds")


class RefreshRequest(BaseSchema):
    """Schema for token refresh request."""

    refresh_token: str = Field(description="JWT refresh token")


class PasswordResetRequest(BaseSchema):
    """Schema for password reset request."""

    email: EmailStr = Field(description="User's email address")


class PasswordResetConfirm(BaseSchema):
    """Schema for password reset confirmation."""

    token: str = Field(description="Password reset token")
    new_password: str = Field(min_length=8, description="New password")

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password contains at least one letter and one number."""
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class WalletLinkRequest(BaseSchema):
    """Schema for linking a Solana wallet to user account."""

    wallet_address: str = Field(
        min_length=32,
        max_length=44,
        description="Solana wallet public key (base58, 32-44 chars)",
    )

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet_address(cls, v: str) -> str:
        """Validate Solana wallet address format (base58, 32-44 chars)."""
        # Solana addresses are base58 encoded and 32-44 characters long
        # Base58 alphabet excludes 0, O, I, l to avoid ambiguity
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", v):
            raise ValueError("Invalid Solana wallet address format")
        return v


class WalletLinkRequestWithSignature(BaseSchema):
    """Schema for linking a Solana wallet with signature verification."""

    wallet_address: str = Field(description="Solana wallet public key (base58)")
    signature: str = Field(description="Signature of the message")
    message: str = Field(description="Message that was signed")

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet_address(cls, v: str) -> str:
        """Validate Solana wallet address format."""
        # Solana addresses are base58 encoded and 32-44 characters long
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", v):
            raise ValueError("Invalid Solana wallet address format")
        return v
