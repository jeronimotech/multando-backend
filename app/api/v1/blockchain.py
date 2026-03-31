"""Blockchain API endpoints.

This module contains FastAPI endpoints for MULTA token operations,
including balance checking, staking, unstaking, and reward claiming.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.blockchain import (
    ClaimRewardsResponse,
    StakeRequest,
    StakingInfoResponse,
    TokenBalanceResponse,
    TokenTransactionList,
    TokenTransactionResponse,
    UnstakeRequest,
)
from app.services.blockchain import BlockchainService

router = APIRouter(prefix="/blockchain", tags=["blockchain"])


@router.get("/balance", response_model=TokenBalanceResponse)
async def get_balance(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TokenBalanceResponse:
    """Get current user's MULTA token balance.

    Returns the user's available balance, staked balance, pending rewards,
    and total lifetime earnings.

    Args:
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        TokenBalanceResponse with balance information.
    """
    service = BlockchainService(db)
    try:
        return await service.get_balance(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/transactions", response_model=TokenTransactionList)
async def get_transactions(
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> TokenTransactionList:
    """Get user's token transaction history.

    Retrieves a paginated list of the user's token transactions,
    including rewards, stakes, unstakes, and transfers.

    Args:
        current_user: The authenticated user.
        page: Page number (1-indexed, default 1).
        page_size: Number of items per page (default 20).
        db: Async database session.

    Returns:
        TokenTransactionList with paginated transactions.
    """
    service = BlockchainService(db)
    transactions, total = await service.get_transactions(
        current_user.id, page, page_size
    )
    return TokenTransactionList(
        items=[TokenTransactionResponse.model_validate(t) for t in transactions],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/stake", response_model=TokenTransactionResponse)
async def stake_tokens(
    request: StakeRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TokenTransactionResponse:
    """Stake MULTA tokens.

    Stakes the specified amount of MULTA tokens. Requires a linked wallet.
    Staked tokens are locked for a minimum period and earn staking rewards.

    Args:
        request: StakeRequest with amount to stake.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        TokenTransactionResponse for the stake transaction.

    Raises:
        HTTPException: 400 if wallet not linked or insufficient balance.
    """
    if not current_user.wallet_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wallet not linked",
        )

    service = BlockchainService(db)
    try:
        tx = await service.stake(current_user.id, request.amount)
        return TokenTransactionResponse.model_validate(tx)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/unstake", response_model=TokenTransactionResponse)
async def unstake_tokens(
    request: UnstakeRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> TokenTransactionResponse:
    """Unstake MULTA tokens.

    Unstakes the specified amount of MULTA tokens. Tokens must be unlocked
    (past the lock period) to be unstaked.

    Args:
        request: UnstakeRequest with amount to unstake.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        TokenTransactionResponse for the unstake transaction.

    Raises:
        HTTPException: 400 if insufficient staked balance or tokens locked.
    """
    service = BlockchainService(db)
    try:
        tx = await service.unstake(current_user.id, request.amount)
        return TokenTransactionResponse.model_validate(tx)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/claim-rewards", response_model=ClaimRewardsResponse)
async def claim_staking_rewards(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ClaimRewardsResponse:
    """Claim staking rewards.

    Claims any pending staking rewards from the user's staking position.
    Rewards are calculated based on the staked amount and time.

    Args:
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        ClaimRewardsResponse with claimed amount and transaction info.

    Raises:
        HTTPException: 400 if no staking position or no rewards to claim.
    """
    service = BlockchainService(db)
    try:
        return await service.claim_rewards(current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/staking-info", response_model=StakingInfoResponse)
async def get_staking_info() -> StakingInfoResponse:
    """Get staking program information.

    Returns general information about the MULTA staking program,
    including APY, minimum stake requirements, and lock periods.

    Returns:
        StakingInfoResponse with staking program details.
    """
    return StakingInfoResponse(
        apy=Decimal("5.0"),
        min_stake=Decimal("10.0"),
        lock_period_days=7,
        total_staked=Decimal("0"),  # Would query from chain in production
        stakers_count=0,  # Would query from chain in production
    )
