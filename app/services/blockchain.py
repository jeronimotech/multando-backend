"""Blockchain service for token operations.

This module contains the BlockchainService class for handling
MULTA token operations, staking, and reward distribution.

In development mode (APP_ENV=development), all operations are simulated
with database-only bookkeeping. In production, real Solana transactions
are submitted via the MultaClient SDK alongside database records.
"""

import logging
import os
import uuid as uuid_module
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Activity, StakingPosition, TokenTransaction, User
from app.models.enums import TokenTxType, TxStatus
from app.models.wallet import CustodialWallet, HotWalletLedger
from app.schemas.blockchain import (
    ClaimRewardsResponse,
    TokenBalanceResponse,
)

if TYPE_CHECKING:
    from multa_sdk import MultaClient

logger = logging.getLogger(__name__)


class BlockchainService:
    """Service for blockchain operations.

    In development mode, simulates token operations.
    In production, uses the Multa SDK for on-chain transactions.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the BlockchainService.

        Args:
            db: Async database session.
        """
        self.db = db
        self.is_dev = os.getenv("APP_ENV", "development") == "development"
        self._multa_client: Optional["MultaClient"] = None

    async def _get_client(self) -> Optional["MultaClient"]:
        """Lazily initialize and return the MultaClient for production use.

        Returns:
            A connected MultaClient instance, or None if not configured.
        """
        if self._multa_client is not None:
            return self._multa_client

        if self.is_dev or not settings.SOLANA_PROGRAM_ID:
            return None

        from multa_sdk import MultaClient
        from solders.keypair import Keypair

        self._multa_client = MultaClient(
            rpc_url=settings.SOLANA_RPC_URL,
            program_id=settings.SOLANA_PROGRAM_ID,
            mint_address=settings.SOLANA_MINT_ADDRESS,
        )
        if settings.SOLANA_REWARD_AUTHORITY_KEY:
            import base58

            key_bytes = base58.b58decode(settings.SOLANA_REWARD_AUTHORITY_KEY)
            self._multa_client.reward_authority_keypair = Keypair.from_bytes(
                key_bytes
            )
        await self._multa_client.connect()
        return self._multa_client

    async def get_balance(self, user_id: UUID) -> TokenBalanceResponse:
        """Get user's token balance.

        In dev mode: calculated from activity records.
        In production: queries on-chain balance when a wallet is linked,
        falls back to database ledger.

        Args:
            user_id: The user's unique identifier.

        Returns:
            TokenBalanceResponse with balance information.

        Raises:
            ValueError: If user not found.
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        # Dev mode: simulate balance from activities
        if self.is_dev:
            return await self._compute_balance_from_db(user_id)

        # Production: try on-chain balance if wallet is available
        if user.wallet_address:
            client = await self._get_client()
            if client:
                try:
                    on_chain_balance = await client.get_balance(user.wallet_address)
                    staking_info = await client.get_staking_position(
                        user.wallet_address
                    )
                    staked = (
                        staking_info["amount"]
                        if staking_info
                        else Decimal(0)
                    )
                    pending_rewards = (
                        staking_info.get("rewards_earned", Decimal(0))
                        if staking_info
                        else Decimal(0)
                    )

                    # Total earned from DB (source of truth for historical totals)
                    result = await self.db.execute(
                        select(Activity).where(Activity.user_id == user_id)
                    )
                    activities = result.scalars().all()
                    total_earned = Decimal(sum(a.multa_earned for a in activities))

                    return TokenBalanceResponse(
                        balance=on_chain_balance,
                        staked_balance=staked,
                        pending_rewards=pending_rewards,
                        total_earned=total_earned,
                    )
                except Exception:
                    logger.warning(
                        "On-chain balance query failed for user %s, "
                        "falling back to DB.",
                        user_id,
                        exc_info=True,
                    )

        # Fallback: compute from database records
        return await self._compute_balance_from_db(user_id)

    async def _compute_balance_from_db(self, user_id: UUID) -> TokenBalanceResponse:
        """Compute balance entirely from database records.

        Args:
            user_id: The user's unique identifier.

        Returns:
            TokenBalanceResponse derived from DB activity and staking records.
        """
        result = await self.db.execute(
            select(Activity).where(Activity.user_id == user_id)
        )
        activities = result.scalars().all()
        total_multa = sum(a.multa_earned for a in activities)

        staking = await self._get_staking_position(user_id)
        staked = Decimal(staking.amount) if staking else Decimal(0)
        pending_rewards = await self._calculate_pending_rewards(staking)

        return TokenBalanceResponse(
            balance=Decimal(total_multa) - staked,
            staked_balance=staked,
            pending_rewards=pending_rewards,
            total_earned=Decimal(total_multa),
        )

    async def get_transactions(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[TokenTransaction], int]:
        """Get user's token transactions.

        Args:
            user_id: The user's unique identifier.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            Tuple of (list of transactions, total count).
        """
        offset = (page - 1) * page_size

        result = await self.db.execute(
            select(TokenTransaction)
            .where(TokenTransaction.user_id == user_id)
            .order_by(desc(TokenTransaction.created_at))
            .offset(offset)
            .limit(page_size)
        )
        transactions = list(result.scalars().all())

        count_result = await self.db.execute(
            select(func.count())
            .select_from(TokenTransaction)
            .where(TokenTransaction.user_id == user_id)
        )
        total = count_result.scalar() or 0

        return transactions, total

    async def stake(self, user_id: UUID, amount: Decimal) -> TokenTransaction:
        """Stake tokens.

        Args:
            user_id: The user's unique identifier.
            amount: Amount of tokens to stake.

        Returns:
            The created TokenTransaction record.

        Raises:
            ValueError: If user has insufficient balance.
        """
        # Verify user has enough balance
        balance = await self.get_balance(user_id)
        if balance.balance < amount:
            raise ValueError("Insufficient balance")

        tx_signature = f"sim_{uuid_module.uuid4().hex[:16]}"
        tx_status = TxStatus.CONFIRMED

        # Production: submit on-chain stake transaction
        if not self.is_dev and settings.SOLANA_PROGRAM_ID:
            user = await self.db.get(User, user_id)
            keypair_bytes = await self._get_user_keypair_bytes(user)
            if keypair_bytes:
                client = await self._get_client()
                if client:
                    try:
                        real_sig = await client.stake(keypair_bytes, amount)
                        tx_signature = real_sig
                    except Exception:
                        logger.error(
                            "On-chain stake failed for user %s",
                            user_id,
                            exc_info=True,
                        )
                        tx_status = TxStatus.FAILED
                        raise ValueError(
                            "On-chain staking transaction failed. "
                            "Please try again later."
                        )

        # Create or update staking position in DB
        position = await self._get_staking_position(user_id)
        if position:
            position.amount = Decimal(position.amount) + amount
        else:
            position = StakingPosition(
                user_id=user_id,
                amount=amount,
                staked_at=datetime.utcnow(),
                unlock_at=datetime.utcnow() + timedelta(days=7),
            )
            self.db.add(position)

        # Record transaction
        tx = TokenTransaction(
            user_id=user_id,
            type=TokenTxType.STAKE,
            amount=amount,
            status=tx_status,
            tx_signature=tx_signature,
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(tx)
        await self.db.commit()

        return tx

    async def unstake(self, user_id: UUID, amount: Decimal) -> TokenTransaction:
        """Unstake tokens.

        Args:
            user_id: The user's unique identifier.
            amount: Amount of tokens to unstake.

        Returns:
            The created TokenTransaction record.

        Raises:
            ValueError: If insufficient staked balance or tokens still locked.
        """
        position = await self._get_staking_position(user_id)
        if not position or Decimal(position.amount) < amount:
            raise ValueError("Insufficient staked balance")

        # Check lock period (7 days)
        if position.unlock_at and position.unlock_at > datetime.utcnow():
            raise ValueError("Tokens still locked")

        tx_signature = f"sim_{uuid_module.uuid4().hex[:16]}"
        tx_status = TxStatus.CONFIRMED

        # Production: submit on-chain unstake transaction
        if not self.is_dev and settings.SOLANA_PROGRAM_ID:
            user = await self.db.get(User, user_id)
            keypair_bytes = await self._get_user_keypair_bytes(user)
            if keypair_bytes:
                client = await self._get_client()
                if client:
                    try:
                        real_sig = await client.unstake(keypair_bytes, amount)
                        tx_signature = real_sig
                    except Exception:
                        logger.error(
                            "On-chain unstake failed for user %s",
                            user_id,
                            exc_info=True,
                        )
                        raise ValueError(
                            "On-chain unstake transaction failed. "
                            "Please try again later."
                        )

        position.amount = Decimal(position.amount) - amount

        tx = TokenTransaction(
            user_id=user_id,
            type=TokenTxType.UNSTAKE,
            amount=amount,
            status=tx_status,
            tx_signature=tx_signature,
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(tx)
        await self.db.commit()

        return tx

    async def claim_rewards(self, user_id: UUID) -> ClaimRewardsResponse:
        """Claim staking rewards.

        Args:
            user_id: The user's unique identifier.

        Returns:
            ClaimRewardsResponse with claimed amount and transaction info.

        Raises:
            ValueError: If no staking position or no rewards to claim.
        """
        position = await self._get_staking_position(user_id)
        if not position:
            raise ValueError("No staking position")

        # Calculate rewards
        rewards = await self._calculate_pending_rewards(position)

        if rewards <= 0:
            raise ValueError("No rewards to claim")

        tx_signature = f"sim_{uuid_module.uuid4().hex[:16]}"

        # Production: submit on-chain claim transaction
        if not self.is_dev and settings.SOLANA_PROGRAM_ID:
            user = await self.db.get(User, user_id)
            keypair_bytes = await self._get_user_keypair_bytes(user)
            if keypair_bytes:
                client = await self._get_client()
                if client:
                    try:
                        real_sig = await client.claim_rewards(keypair_bytes)
                        tx_signature = real_sig
                    except Exception:
                        logger.error(
                            "On-chain claim_rewards failed for user %s",
                            user_id,
                            exc_info=True,
                        )
                        raise ValueError(
                            "On-chain rewards claim failed. "
                            "Please try again later."
                        )

        tx = TokenTransaction(
            user_id=user_id,
            type=TokenTxType.REWARD,
            amount=rewards,
            status=TxStatus.CONFIRMED,
            tx_signature=tx_signature,
            confirmed_at=datetime.utcnow(),
        )
        self.db.add(tx)

        position.last_claim_at = datetime.utcnow()
        position.rewards_claimed = Decimal(position.rewards_claimed) + rewards

        await self.db.commit()

        # Get updated balance
        balance = await self.get_balance(user_id)

        return ClaimRewardsResponse(
            amount_claimed=rewards,
            tx_signature=tx.tx_signature,
            new_balance=balance.balance,
        )

    async def distribute_reward(
        self,
        user_id: UUID,
        amount: Decimal,
        activity_id: int,
    ) -> TokenTransaction:
        """Distribute reward to user (called by gamification service).

        Writes to the database unconditionally. When Solana config is set
        and we are not in dev mode, also submits a real on-chain transaction.

        Args:
            user_id: The user's unique identifier.
            amount: Amount of tokens to reward.
            activity_id: Associated activity ID.

        Returns:
            The created TokenTransaction record.
        """
        tx = TokenTransaction(
            user_id=user_id,
            type=TokenTxType.REWARD,
            amount=amount,
            activity_id=activity_id,
            status=TxStatus.CONFIRMED,
            tx_signature=f"sim_{uuid_module.uuid4().hex[:16]}",
            confirmed_at=datetime.utcnow(),
        )

        # Production: submit real on-chain reward distribution
        if not self.is_dev and settings.SOLANA_PROGRAM_ID:
            user = await self.db.get(User, user_id)
            if user and user.wallet_address:
                client = await self._get_client()
                if client:
                    try:
                        real_sig = await client.distribute_reward(
                            recipient=user.wallet_address,
                            amount=amount,
                            activity_id=str(activity_id),
                        )
                        tx.tx_signature = real_sig
                    except Exception:
                        logger.error(
                            "On-chain distribute_reward failed for user %s, "
                            "activity %s. DB record created with simulated sig.",
                            user_id,
                            activity_id,
                            exc_info=True,
                        )
                        tx.status = TxStatus.PENDING
            else:
                logger.info(
                    "User %s has no wallet_address; reward recorded in DB only.",
                    user_id,
                )

        self.db.add(tx)
        await self.db.commit()
        return tx

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_user_keypair_bytes(self, user) -> Optional[bytes]:
        """Decrypt custodial wallet keypair for a user.

        Args:
            user: User model instance.

        Returns:
            Raw 64-byte keypair or None if no custodial wallet.
        """
        if not user:
            return None

        result = await self.db.execute(
            select(CustodialWallet).where(CustodialWallet.user_id == user.id)
        )
        wallet = result.scalar_one_or_none()
        if not wallet:
            return None

        from app.core.encryption import decrypt_wallet_key

        try:
            return decrypt_wallet_key(
                wallet.encrypted_private_key,
                wallet.encrypted_dek,
                wallet.iv,
            )
        except Exception:
            logger.error(
                "Failed to decrypt wallet for user %s",
                user.id,
                exc_info=True,
            )
            return None

    async def _get_staking_position(self, user_id: UUID) -> StakingPosition | None:
        """Get user's active staking position.

        Args:
            user_id: The user's unique identifier.

        Returns:
            StakingPosition if found, None otherwise.
        """
        result = await self.db.execute(
            select(StakingPosition)
            .where(StakingPosition.user_id == user_id)
            .where(StakingPosition.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def _calculate_pending_rewards(
        self, position: StakingPosition | None
    ) -> Decimal:
        """Calculate pending staking rewards.

        Simplified calculation: 5% APY, calculated daily.
        In production, this would be more sophisticated.

        Args:
            position: The user's staking position.

        Returns:
            Pending rewards amount.
        """
        if not position:
            return Decimal(0)

        # Calculate days since last claim or staking start
        last_claim = position.last_claim_at or position.staked_at
        days_elapsed = (datetime.utcnow() - last_claim).days

        if days_elapsed <= 0:
            return Decimal(0)

        # 5% APY = 0.05 / 365 per day
        daily_rate = Decimal("0.05") / Decimal("365")
        rewards = Decimal(position.amount) * daily_rate * Decimal(days_elapsed)

        return rewards.quantize(Decimal("0.000001"))
