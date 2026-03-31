"""Wallet schemas for the Multando API.

This module contains schemas for custodial wallet operations,
including wallet info, mode switching, withdrawals, and limits.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema


class WalletInfoResponse(BaseSchema):
    """Schema for wallet information response."""

    wallet_type: str = Field(description="Wallet type: 'custodial' or 'self_custodial'")
    public_key: str | None = Field(
        default=None, description="Wallet public key / address"
    )
    status: str = Field(description="Wallet status: 'active', 'frozen', or 'deactivated'")
    balance: Decimal = Field(ge=0, description="Available token balance")
    staked_balance: Decimal = Field(ge=0, description="Staked token balance")
    pending_rewards: Decimal = Field(ge=0, description="Pending staking rewards")
    total_earned: Decimal = Field(ge=0, description="Total tokens earned lifetime")
    can_withdraw: bool = Field(description="Whether user can currently withdraw")


class SwitchModeRequest(BaseSchema):
    """Schema for switching wallet mode."""

    mode: str = Field(description="Target mode: 'custodial' or 'self_custodial'")
    wallet_address: str | None = Field(
        default=None,
        description="External wallet address (required for self_custodial)",
    )

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        """Validate mode is a supported wallet type."""
        if v not in ("custodial", "self_custodial"):
            raise ValueError("Mode must be 'custodial' or 'self_custodial'")
        return v


class WithdrawalCreateRequest(BaseSchema):
    """Schema for creating a withdrawal request."""

    amount: Decimal = Field(gt=0, description="Amount to withdraw")
    destination_address: str = Field(
        min_length=32,
        max_length=44,
        description="Destination Solana wallet address (base58)",
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Validate withdrawal amount precision."""
        if v.as_tuple().exponent < -6:
            raise ValueError("Amount cannot have more than 6 decimal places")
        return v

    @field_validator("destination_address")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        """Validate destination is a plausible base58 Solana address."""
        import re

        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", v):
            raise ValueError("Invalid Solana address: must be base58 encoded, 32-44 characters")
        return v


class WithdrawalVerifyRequest(BaseSchema):
    """Schema for verifying a withdrawal with OTP."""

    withdrawal_id: int = Field(description="ID of the withdrawal to verify")
    code: str = Field(
        min_length=6, max_length=6, description="6-digit verification code"
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        """Validate code is exactly 6 digits."""
        if not v.isdigit():
            raise ValueError("Verification code must contain only digits")
        return v


class WithdrawalResponse(BaseSchema):
    """Schema for a single withdrawal response."""

    id: int = Field(description="Withdrawal ID")
    amount: Decimal = Field(description="Withdrawal amount")
    destination_address: str = Field(description="Destination wallet address")
    status: str = Field(description="Withdrawal status")
    tx_signature: str | None = Field(
        default=None, description="On-chain transaction signature"
    )
    fee_amount: Decimal = Field(description="Fee charged for the withdrawal")
    created_at: datetime = Field(description="When the withdrawal was requested")
    processed_at: datetime | None = Field(
        default=None, description="When the withdrawal was processed"
    )


class WithdrawalListResponse(BaseSchema):
    """Schema for paginated list of withdrawals."""

    items: list[WithdrawalResponse] = Field(description="List of withdrawals")
    total: int = Field(description="Total number of withdrawals")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")


class WithdrawalLimitsResponse(BaseSchema):
    """Schema for withdrawal limits and usage."""

    daily_limit: Decimal = Field(description="Maximum daily withdrawal amount")
    monthly_limit: Decimal = Field(description="Maximum monthly withdrawal amount")
    daily_used: Decimal = Field(description="Amount withdrawn in last 24 hours")
    monthly_used: Decimal = Field(description="Amount withdrawn in last 30 days")
    daily_remaining: Decimal = Field(description="Remaining daily withdrawal allowance")
    monthly_remaining: Decimal = Field(
        description="Remaining monthly withdrawal allowance"
    )
    withdrawal_fee: Decimal = Field(description="Fee per withdrawal")
    verification_threshold: Decimal = Field(
        description="Amount above which OTP verification is required"
    )
