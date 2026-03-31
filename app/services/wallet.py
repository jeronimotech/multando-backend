"""Custodial wallet service for managing user wallets and withdrawals.

This service handles custodial wallet creation, mode switching between
custodial and self-custodial wallets, withdrawal requests with OTP
verification, and limit enforcement.
"""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import encrypt_wallet_key
from app.models.activity import StakingPosition
from app.models.enums import WalletStatus, WalletType, WithdrawalStatus
from app.models.user import User
from app.models.wallet import CustodialWallet, HotWalletLedger, WithdrawalRequest
from app.schemas.wallet import WalletInfoResponse, WithdrawalLimitsResponse


class WalletService:
    """Service for custodial wallet operations.

    Provides methods for wallet creation, mode switching, withdrawal
    requests, OTP verification, and limit checking.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the wallet service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def create_custodial_wallet(self, user_id: UUID) -> CustodialWallet:
        """Create a new custodial wallet for a user.

        Generates a simulated keypair, encrypts the private key using
        envelope encryption, and creates the wallet record along with
        a zero-balance ledger entry.

        Args:
            user_id: UUID of the user to create the wallet for.

        Returns:
            The newly created CustodialWallet object.
        """
        # Generate a simulated 64-byte secret (in production, use actual Solana Keypair)
        secret_bytes = secrets.token_bytes(64)

        # Derive a public key as hex of first 32 bytes (simulated)
        public_key = secret_bytes[:32].hex()

        # Encrypt the private key using envelope encryption
        encrypted_pk, encrypted_dek, iv = encrypt_wallet_key(secret_bytes)

        # Create the custodial wallet record
        wallet = CustodialWallet(
            user_id=user_id,
            public_key=public_key,
            encrypted_private_key=encrypted_pk,
            encrypted_dek=encrypted_dek,
            iv=iv,
            encryption_version=1,
            status=WalletStatus.ACTIVE,
        )
        self.db.add(wallet)

        # Update the user's wallet_address
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()
        user.wallet_address = public_key

        # Create a zero-balance ledger entry
        ledger = HotWalletLedger(
            user_id=user_id,
            balance=Decimal("0"),
        )
        self.db.add(ledger)

        await self.db.flush()
        await self.db.refresh(wallet)
        return wallet

    async def get_wallet_info(self, user_id: UUID) -> WalletInfoResponse:
        """Get wallet information for a user.

        Returns balance, staking, and status information depending on
        whether the user has a custodial or self-custodial wallet.

        Args:
            user_id: UUID of the user.

        Returns:
            WalletInfoResponse with wallet details.

        Raises:
            ValueError: If user is not found.
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        balance = Decimal("0")
        staked_balance = Decimal("0")
        pending_rewards = Decimal("0")
        total_earned = Decimal("0")
        wallet_status = "active"
        can_withdraw = False
        public_key = user.wallet_address

        if user.wallet_type == WalletType.CUSTODIAL:
            # Get custodial wallet status
            wallet_result = await self.db.execute(
                select(CustodialWallet).where(CustodialWallet.user_id == user_id)
            )
            wallet = wallet_result.scalar_one_or_none()
            if wallet:
                wallet_status = wallet.status.value
                public_key = wallet.public_key

            # Get ledger balance
            ledger_result = await self.db.execute(
                select(HotWalletLedger).where(HotWalletLedger.user_id == user_id)
            )
            ledger = ledger_result.scalar_one_or_none()
            if ledger:
                balance = ledger.balance

            can_withdraw = (
                wallet is not None
                and wallet.status == WalletStatus.ACTIVE
                and balance > 0
            )
        else:
            # Self-custodial: wallet status is always "active" from our perspective
            wallet_status = "active"

        # Get staking info (common for both wallet types)
        staking_result = await self.db.execute(
            select(StakingPosition).where(
                StakingPosition.user_id == user_id,
                StakingPosition.is_active.is_(True),
            )
        )
        staking_positions = staking_result.scalars().all()
        for pos in staking_positions:
            staked_balance += pos.amount
            pending_rewards += pos.rewards_claimed  # accumulated rewards

        # Calculate total earned from ledger balance + staked + rewards
        total_earned = balance + staked_balance + pending_rewards

        return WalletInfoResponse(
            wallet_type=user.wallet_type.value,
            public_key=public_key,
            status=wallet_status,
            balance=balance,
            staked_balance=staked_balance,
            pending_rewards=pending_rewards,
            total_earned=total_earned,
            can_withdraw=can_withdraw,
        )

    async def switch_to_self_custodial(
        self, user_id: UUID, external_address: str
    ) -> User:
        """Switch a user from custodial to self-custodial wallet mode.

        The user must withdraw all funds from their custodial wallet
        before switching. The custodial wallet is deactivated but not
        deleted, allowing reactivation later.

        Args:
            user_id: UUID of the user.
            external_address: The user's external Solana wallet address.

        Returns:
            The updated User object.

        Raises:
            ValueError: If address is invalid or balance is non-zero.
        """
        import re

        # Validate external address format (base58, 32-44 chars)
        if not re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", external_address):
            raise ValueError(
                "Invalid Solana address: must be base58 encoded, 32-44 characters"
            )

        # Check that ledger balance is zero
        ledger_result = await self.db.execute(
            select(HotWalletLedger).where(HotWalletLedger.user_id == user_id)
        )
        ledger = ledger_result.scalar_one_or_none()
        if ledger and ledger.balance > Decimal("0"):
            raise ValueError(
                "Must withdraw all funds before switching to self-custodial mode"
            )

        # Deactivate the custodial wallet
        wallet_result = await self.db.execute(
            select(CustodialWallet).where(CustodialWallet.user_id == user_id)
        )
        wallet = wallet_result.scalar_one_or_none()
        if wallet:
            wallet.status = WalletStatus.DEACTIVATED

        # Update user
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        user.wallet_type = WalletType.SELF_CUSTODIAL
        user.wallet_address = external_address

        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def switch_to_custodial(self, user_id: UUID) -> User:
        """Switch a user from self-custodial to custodial wallet mode.

        If a custodial wallet previously existed and was deactivated,
        it will be reactivated. Otherwise, a new one is created.

        Args:
            user_id: UUID of the user.

        Returns:
            The updated User object.
        """
        # Check for existing deactivated wallet
        wallet_result = await self.db.execute(
            select(CustodialWallet).where(CustodialWallet.user_id == user_id)
        )
        wallet = wallet_result.scalar_one_or_none()

        if wallet and wallet.status == WalletStatus.DEACTIVATED:
            # Reactivate existing wallet
            wallet.status = WalletStatus.ACTIVE

            # Restore wallet address on user
            user_result = await self.db.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one()
            user.wallet_type = WalletType.CUSTODIAL
            user.wallet_address = wallet.public_key

            await self.db.flush()
            await self.db.refresh(user)
            return user

        if not wallet:
            # Create a brand-new custodial wallet
            await self.create_custodial_wallet(user_id)

        # Update user wallet type
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one()
        user.wallet_type = WalletType.CUSTODIAL

        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def request_withdrawal(
        self,
        user_id: UUID,
        amount: Decimal,
        destination: str,
        ip: str,
    ) -> WithdrawalRequest:
        """Create a withdrawal request from the custodial wallet.

        Validates the user has a custodial wallet, sufficient balance,
        and has not exceeded daily/monthly limits. A fee is deducted,
        and large withdrawals require OTP verification.

        Args:
            user_id: UUID of the user.
            amount: Amount to withdraw (before fee).
            destination: Destination Solana wallet address.
            ip: IP address of the request origin.

        Returns:
            The created WithdrawalRequest object.

        Raises:
            ValueError: If validation fails (wrong wallet type, insufficient
                balance, limit exceeded, etc.).
        """
        # Verify user has custodial wallet
        user_result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")
        if user.wallet_type != WalletType.CUSTODIAL:
            raise ValueError("Withdrawals are only available for custodial wallets")

        # Validate amount
        if amount <= Decimal("0"):
            raise ValueError("Withdrawal amount must be greater than zero")

        fee = Decimal(str(settings.WITHDRAWAL_FEE))
        total_deduction = amount + fee

        # Check sufficient balance in ledger
        ledger_result = await self.db.execute(
            select(HotWalletLedger).where(HotWalletLedger.user_id == user_id)
        )
        ledger = ledger_result.scalar_one_or_none()
        if not ledger or ledger.balance < total_deduction:
            raise ValueError("Insufficient balance for withdrawal and fee")

        # Check daily/monthly limits
        await self._check_limits(user_id, amount)

        # Determine if OTP verification is needed
        verification_threshold = Decimal(str(settings.WITHDRAWAL_VERIFICATION_THRESHOLD))
        if amount > verification_threshold:
            otp_code = f"{secrets.randbelow(1000000):06d}"
            verification_expires = datetime.now(timezone.utc) + timedelta(minutes=10)
            withdrawal_status = WithdrawalStatus.PENDING_VERIFICATION
        else:
            otp_code = None
            verification_expires = None
            withdrawal_status = WithdrawalStatus.PENDING

        # Create the withdrawal request
        withdrawal = WithdrawalRequest(
            user_id=user_id,
            amount=amount,
            destination_address=destination,
            status=withdrawal_status,
            fee_amount=fee,
            verification_code=otp_code,
            verification_expires_at=verification_expires,
            ip_address=ip,
        )
        self.db.add(withdrawal)

        # Deduct from ledger (amount + fee)
        ledger.balance -= total_deduction

        await self.db.flush()
        await self.db.refresh(withdrawal)
        return withdrawal

    async def verify_withdrawal(
        self, user_id: UUID, withdrawal_id: int, code: str
    ) -> WithdrawalRequest:
        """Verify a withdrawal request using an OTP code.

        Args:
            user_id: UUID of the user.
            withdrawal_id: ID of the withdrawal to verify.
            code: The 6-digit OTP code.

        Returns:
            The updated WithdrawalRequest object.

        Raises:
            ValueError: If verification fails (wrong code, expired, wrong status).
        """
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == withdrawal_id,
                WithdrawalRequest.user_id == user_id,
            )
        )
        withdrawal = result.scalar_one_or_none()
        if not withdrawal:
            raise ValueError("Withdrawal request not found")

        if withdrawal.status != WithdrawalStatus.PENDING_VERIFICATION:
            raise ValueError("Withdrawal is not pending verification")

        # Check expiry
        if (
            withdrawal.verification_expires_at
            and datetime.now(timezone.utc) > withdrawal.verification_expires_at
        ):
            raise ValueError("Verification code has expired")

        # Check code
        if withdrawal.verification_code != code:
            raise ValueError("Invalid verification code")

        # Advance to PENDING for processing
        withdrawal.status = WithdrawalStatus.PENDING
        withdrawal.verification_code = None
        withdrawal.verification_expires_at = None

        await self.db.flush()
        await self.db.refresh(withdrawal)
        return withdrawal

    async def cancel_withdrawal(
        self, user_id: UUID, withdrawal_id: int
    ) -> WithdrawalRequest:
        """Cancel a pending withdrawal and refund the balance.

        Args:
            user_id: UUID of the user.
            withdrawal_id: ID of the withdrawal to cancel.

        Returns:
            The updated WithdrawalRequest object.

        Raises:
            ValueError: If withdrawal cannot be cancelled.
        """
        result = await self.db.execute(
            select(WithdrawalRequest).where(
                WithdrawalRequest.id == withdrawal_id,
                WithdrawalRequest.user_id == user_id,
            )
        )
        withdrawal = result.scalar_one_or_none()
        if not withdrawal:
            raise ValueError("Withdrawal request not found")

        cancellable_statuses = (
            WithdrawalStatus.PENDING,
            WithdrawalStatus.PENDING_VERIFICATION,
        )
        if withdrawal.status not in cancellable_statuses:
            raise ValueError(
                f"Cannot cancel withdrawal with status '{withdrawal.status.value}'"
            )

        # Refund amount + fee to ledger
        refund_amount = withdrawal.amount + withdrawal.fee_amount
        ledger_result = await self.db.execute(
            select(HotWalletLedger).where(HotWalletLedger.user_id == user_id)
        )
        ledger = ledger_result.scalar_one_or_none()
        if ledger:
            ledger.balance += refund_amount

        withdrawal.status = WithdrawalStatus.CANCELLED

        await self.db.flush()
        await self.db.refresh(withdrawal)
        return withdrawal

    async def get_withdrawal_history(
        self, user_id: UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[WithdrawalRequest], int]:
        """Get paginated withdrawal history for a user.

        Args:
            user_id: UUID of the user.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Tuple of (list of WithdrawalRequest, total count).
        """
        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(WithdrawalRequest).where(
                WithdrawalRequest.user_id == user_id
            )
        )
        total = count_result.scalar_one()

        # Fetch page
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(WithdrawalRequest)
            .where(WithdrawalRequest.user_id == user_id)
            .order_by(WithdrawalRequest.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        items = list(result.scalars().all())

        return items, total

    async def get_withdrawal_limits(self, user_id: UUID) -> WithdrawalLimitsResponse:
        """Get withdrawal limits and current usage for a user.

        Calculates daily and monthly usage by summing non-cancelled,
        non-failed withdrawals within the respective time windows.

        Args:
            user_id: UUID of the user.

        Returns:
            WithdrawalLimitsResponse with limits and remaining amounts.
        """
        daily_limit = Decimal(str(settings.WITHDRAWAL_DAILY_LIMIT))
        monthly_limit = Decimal(str(settings.WITHDRAWAL_MONTHLY_LIMIT))
        fee = Decimal(str(settings.WITHDRAWAL_FEE))
        verification_threshold = Decimal(str(settings.WITHDRAWAL_VERIFICATION_THRESHOLD))

        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(hours=24)
        month_ago = now - timedelta(days=30)

        excluded_statuses = (WithdrawalStatus.CANCELLED, WithdrawalStatus.FAILED)

        # Daily usage
        daily_result = await self.db.execute(
            select(func.coalesce(func.sum(WithdrawalRequest.amount), Decimal("0")))
            .where(
                WithdrawalRequest.user_id == user_id,
                WithdrawalRequest.created_at >= day_ago,
                WithdrawalRequest.status.notin_(excluded_statuses),
            )
        )
        daily_used = daily_result.scalar_one()

        # Monthly usage
        monthly_result = await self.db.execute(
            select(func.coalesce(func.sum(WithdrawalRequest.amount), Decimal("0")))
            .where(
                WithdrawalRequest.user_id == user_id,
                WithdrawalRequest.created_at >= month_ago,
                WithdrawalRequest.status.notin_(excluded_statuses),
            )
        )
        monthly_used = monthly_result.scalar_one()

        daily_remaining = max(daily_limit - daily_used, Decimal("0"))
        monthly_remaining = max(monthly_limit - monthly_used, Decimal("0"))

        return WithdrawalLimitsResponse(
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
            daily_used=daily_used,
            monthly_used=monthly_used,
            daily_remaining=daily_remaining,
            monthly_remaining=monthly_remaining,
            withdrawal_fee=fee,
            verification_threshold=verification_threshold,
        )

    async def _check_limits(self, user_id: UUID, amount: Decimal) -> None:
        """Check that a withdrawal amount does not exceed daily or monthly limits.

        Args:
            user_id: UUID of the user.
            amount: The proposed withdrawal amount.

        Raises:
            ValueError: If daily or monthly limit would be exceeded.
        """
        limits = await self.get_withdrawal_limits(user_id)

        if amount > limits.daily_remaining:
            raise ValueError(
                f"Daily withdrawal limit exceeded. "
                f"Remaining: {limits.daily_remaining}, requested: {amount}"
            )

        if amount > limits.monthly_remaining:
            raise ValueError(
                f"Monthly withdrawal limit exceeded. "
                f"Remaining: {limits.monthly_remaining}, requested: {amount}"
            )
