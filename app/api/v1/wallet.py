"""Wallet API endpoints.

This module contains FastAPI endpoints for custodial wallet operations,
including wallet info, mode switching, withdrawals, and limits.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.wallet import (
    SwitchModeRequest,
    WalletInfoResponse,
    WithdrawalCreateRequest,
    WithdrawalLimitsResponse,
    WithdrawalListResponse,
    WithdrawalResponse,
    WithdrawalVerifyRequest,
)
from app.services.wallet import WalletService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["wallet"])


@router.get("/info", response_model=WalletInfoResponse)
async def get_wallet_info(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WalletInfoResponse:
    """Get current user's wallet information.

    Returns wallet type, balance, staking information, and withdrawal
    eligibility based on the user's wallet configuration.

    Args:
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        WalletInfoResponse with wallet details.
    """
    service = WalletService(db)
    try:
        return await service.get_wallet_info(current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception:
        logger.exception("Failed to get wallet info for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve wallet information",
        )


@router.post("/switch-mode", response_model=WalletInfoResponse)
async def switch_wallet_mode(
    request: SwitchModeRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WalletInfoResponse:
    """Switch between custodial and self-custodial wallet modes.

    When switching to self-custodial, the user must provide an external
    wallet address and have a zero custodial balance. When switching
    to custodial, the previous wallet is reactivated or a new one is created.

    Args:
        request: SwitchModeRequest with target mode and optional address.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        WalletInfoResponse reflecting the new wallet state.
    """
    service = WalletService(db)
    try:
        if request.mode == "self_custodial":
            if not request.wallet_address:
                raise ValueError(
                    "wallet_address is required when switching to self-custodial mode"
                )
            await service.switch_to_self_custodial(
                current_user.id, request.wallet_address
            )
        else:
            await service.switch_to_custodial(current_user.id)

        return await service.get_wallet_info(current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception:
        logger.exception(
            "Failed to switch wallet mode for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to switch wallet mode",
        )


@router.post("/withdraw", response_model=WithdrawalResponse)
async def create_withdrawal(
    body: WithdrawalCreateRequest,
    http_request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WithdrawalResponse:
    """Request a withdrawal from the custodial wallet.

    Creates a withdrawal request. If the amount exceeds the verification
    threshold, OTP verification will be required before processing.

    Args:
        body: WithdrawalCreateRequest with amount and destination.
        http_request: The raw HTTP request (for client IP).
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        WithdrawalResponse with the created withdrawal details.
    """
    service = WalletService(db)
    client_ip = http_request.client.host if http_request.client else "unknown"
    try:
        withdrawal = await service.request_withdrawal(
            user_id=current_user.id,
            amount=body.amount,
            destination=body.destination_address,
            ip=client_ip,
        )
        return WithdrawalResponse.model_validate(withdrawal)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception:
        logger.exception(
            "Failed to create withdrawal for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create withdrawal request",
        )


@router.post("/withdraw/verify", response_model=WithdrawalResponse)
async def verify_withdrawal(
    body: WithdrawalVerifyRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WithdrawalResponse:
    """Verify a withdrawal request using an OTP code.

    Required for withdrawals exceeding the verification threshold.
    The code is valid for 10 minutes from the withdrawal creation.

    Args:
        body: WithdrawalVerifyRequest with withdrawal ID and OTP code.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        WithdrawalResponse with the updated withdrawal details.
    """
    service = WalletService(db)
    try:
        withdrawal = await service.verify_withdrawal(
            user_id=current_user.id,
            withdrawal_id=body.withdrawal_id,
            code=body.code,
        )
        return WithdrawalResponse.model_validate(withdrawal)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception:
        logger.exception(
            "Failed to verify withdrawal %s for user %s",
            body.withdrawal_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify withdrawal",
        )


@router.delete("/withdraw/{withdrawal_id}", response_model=WithdrawalResponse)
async def cancel_withdrawal(
    withdrawal_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WithdrawalResponse:
    """Cancel a pending withdrawal and refund the balance.

    Only withdrawals with status PENDING or PENDING_VERIFICATION can
    be cancelled. The full amount plus fee is refunded to the ledger.

    Args:
        withdrawal_id: ID of the withdrawal to cancel.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        WithdrawalResponse with the cancelled withdrawal details.
    """
    service = WalletService(db)
    try:
        withdrawal = await service.cancel_withdrawal(
            user_id=current_user.id,
            withdrawal_id=withdrawal_id,
        )
        return WithdrawalResponse.model_validate(withdrawal)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception:
        logger.exception(
            "Failed to cancel withdrawal %s for user %s",
            withdrawal_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel withdrawal",
        )


@router.get("/withdrawals", response_model=WithdrawalListResponse)
async def get_withdrawal_history(
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> WithdrawalListResponse:
    """Get the user's withdrawal history.

    Returns a paginated list of all withdrawal requests, ordered by
    creation date (newest first).

    Args:
        current_user: The authenticated user.
        page: Page number (1-indexed, default 1).
        page_size: Number of items per page (default 20).
        db: Async database session.

    Returns:
        WithdrawalListResponse with paginated withdrawal records.
    """
    service = WalletService(db)
    try:
        items, total = await service.get_withdrawal_history(
            current_user.id, page, page_size
        )
        return WithdrawalListResponse(
            items=[WithdrawalResponse.model_validate(w) for w in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception(
            "Failed to get withdrawal history for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve withdrawal history",
        )


@router.get("/limits", response_model=WithdrawalLimitsResponse)
async def get_withdrawal_limits(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> WithdrawalLimitsResponse:
    """Get the user's withdrawal limits and current usage.

    Returns daily and monthly limits, current usage, remaining
    allowances, fee amount, and verification threshold.

    Args:
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        WithdrawalLimitsResponse with limits and usage data.
    """
    service = WalletService(db)
    try:
        return await service.get_withdrawal_limits(current_user.id)
    except Exception:
        logger.exception(
            "Failed to get withdrawal limits for user %s", current_user.id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve withdrawal limits",
        )
