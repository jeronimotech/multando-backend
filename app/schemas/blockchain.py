"""Blockchain schemas for the Multando API.

This module contains schemas for token operations, staking, and blockchain interactions.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field, field_validator

from app.models.enums import TokenTxType, TxStatus
from app.schemas.base import BaseSchema


class TokenBalanceResponse(BaseSchema):
    """Schema for token balance response."""

    balance: Decimal = Field(ge=0, description="Available MULTA token balance")
    staked_balance: Decimal = Field(ge=0, description="Staked MULTA token balance")
    pending_rewards: Decimal = Field(ge=0, description="Pending staking rewards")
    total_earned: Decimal = Field(
        default=Decimal("0"), ge=0, description="Total MULTA earned lifetime"
    )


class TokenTransactionBase(BaseSchema):
    """Base schema for token transaction data."""

    type: TokenTxType = Field(description="Type of transaction")
    amount: Decimal = Field(ge=0, description="Transaction amount")
    tx_signature: str | None = Field(
        default=None, description="Solana transaction signature"
    )
    status: TxStatus = Field(description="Transaction status")


class TokenTransactionResponse(TokenTransactionBase):
    """Schema for token transaction response."""

    id: int = Field(description="Transaction unique identifier")
    created_at: datetime = Field(description="When the transaction was created")
    confirmed_at: datetime | None = Field(
        default=None, description="When the transaction was confirmed"
    )


class TokenTransactionList(BaseSchema):
    """Schema for paginated list of token transactions."""

    items: list[TokenTransactionResponse] = Field(description="List of transactions")
    total: int = Field(description="Total number of transactions")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")


class StakeRequest(BaseSchema):
    """Schema for staking tokens request."""

    amount: Decimal = Field(gt=0, description="Amount of MULTA tokens to stake")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Validate stake amount has at most 9 decimal places (Solana precision)."""
        if v.as_tuple().exponent < -9:
            raise ValueError("Amount cannot have more than 9 decimal places")
        return v


class UnstakeRequest(BaseSchema):
    """Schema for unstaking tokens request."""

    amount: Decimal = Field(gt=0, description="Amount of MULTA tokens to unstake")

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Validate unstake amount has at most 9 decimal places (Solana precision)."""
        if v.as_tuple().exponent < -9:
            raise ValueError("Amount cannot have more than 9 decimal places")
        return v


class ClaimRewardsResponse(BaseSchema):
    """Schema for claiming staking rewards response."""

    amount_claimed: Decimal = Field(ge=0, description="Amount of rewards claimed")
    tx_signature: str | None = Field(
        default=None, description="Solana transaction signature"
    )
    new_balance: Decimal = Field(ge=0, description="New token balance after claiming")


class StakingInfoResponse(BaseSchema):
    """Schema for staking program information response."""

    apy: Decimal = Field(ge=0, description="Current annual percentage yield")
    min_stake: Decimal = Field(ge=0, description="Minimum amount required to stake")
    lock_period_days: int = Field(ge=0, description="Lock period in days")
    total_staked: Decimal = Field(ge=0, description="Total MULTA staked in the program")
    stakers_count: int = Field(ge=0, description="Number of active stakers")


class UserStakingInfoResponse(BaseSchema):
    """Schema for user-specific staking information response."""

    staked_amount: Decimal = Field(ge=0, description="Currently staked amount")
    pending_rewards: Decimal = Field(ge=0, description="Pending rewards to claim")
    apy: Decimal = Field(ge=0, description="Current annual percentage yield")
    staking_start: datetime | None = Field(
        default=None, description="When staking started"
    )
    lock_end: datetime | None = Field(
        default=None, description="When staking lock period ends (if applicable)"
    )
    can_unstake: bool = Field(description="Whether user can currently unstake")


class NFTMintRequest(BaseSchema):
    """Schema for NFT minting request."""

    badge_id: UUID = Field(description="ID of the badge to mint as NFT")


class NFTMintResponse(BaseSchema):
    """Schema for NFT minting response."""

    mint_address: str = Field(description="Solana NFT mint address")
    tx_signature: str = Field(description="Solana transaction signature")
    metadata_uri: str = Field(description="URI to NFT metadata")
