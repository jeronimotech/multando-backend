"""Celery task definitions for background processing."""

import asyncio
import logging
from decimal import Decimal

from app.core.celery import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.tasks.cleanup_expired_conversations")
def cleanup_expired_conversations() -> dict:
    """Clean up expired WhatsApp conversation contexts.

    Removes conversation contexts that have been inactive
    for more than 30 minutes.

    Returns:
        Dict with count of cleaned conversations.
    """
    logger.info("Running conversation cleanup task")
    # In production, this would connect to Redis/DB and clean up
    # For now, the ConversationService does in-memory cleanup
    return {"cleaned": 0}


@celery_app.task(name="app.tasks.sync_blockchain_balances")
def sync_blockchain_balances() -> dict:
    """Reconcile on-chain token balances with database records.

    For every user with a wallet_address, queries the Solana RPC for
    their real MULTA balance and compares with the HotWalletLedger.
    Discrepancies are logged as warnings.

    Returns:
        Dict with sync statistics.
    """
    logger.info("Running blockchain balance sync task")

    if not settings.SOLANA_PROGRAM_ID or not settings.SOLANA_MINT_ADDRESS:
        logger.info("Solana not configured; skipping balance sync.")
        return {"synced": 0, "skipped": True}

    return _run_async(_sync_blockchain_balances_async())


async def _sync_blockchain_balances_async() -> dict:
    """Async implementation of the balance sync task."""
    from sqlalchemy import select

    from app.core.database import async_session_maker
    from app.models.user import User
    from app.models.wallet import HotWalletLedger
    from multa_sdk import MultaClient

    client = MultaClient(
        rpc_url=settings.SOLANA_RPC_URL,
        program_id=settings.SOLANA_PROGRAM_ID,
        mint_address=settings.SOLANA_MINT_ADDRESS,
    )
    await client.connect()

    stats = {
        "total_users": 0,
        "synced": 0,
        "discrepancies": 0,
        "errors": 0,
    }

    try:
        async with async_session_maker() as session:
            # Fetch all users that have a wallet address
            result = await session.execute(
                select(User).where(User.wallet_address.isnot(None))
            )
            users = result.scalars().all()
            stats["total_users"] = len(users)

            for user in users:
                try:
                    # Query on-chain balance
                    on_chain_balance = await client.get_balance(user.wallet_address)

                    # Query DB ledger balance
                    ledger_result = await session.execute(
                        select(HotWalletLedger).where(
                            HotWalletLedger.user_id == user.id
                        )
                    )
                    ledger = ledger_result.scalar_one_or_none()
                    db_balance = Decimal(ledger.balance) if ledger else Decimal(0)

                    # Compare (allow small rounding tolerance)
                    diff = abs(on_chain_balance - db_balance)
                    tolerance = Decimal("0.001")

                    if diff > tolerance:
                        stats["discrepancies"] += 1
                        logger.warning(
                            "Balance discrepancy for user %s (wallet %s): "
                            "on-chain=%s db=%s diff=%s",
                            user.id,
                            user.wallet_address,
                            on_chain_balance,
                            db_balance,
                            diff,
                        )
                    else:
                        stats["synced"] += 1

                except Exception:
                    stats["errors"] += 1
                    logger.error(
                        "Error syncing balance for user %s",
                        user.id,
                        exc_info=True,
                    )
    finally:
        await client.disconnect()

    logger.info(
        "Balance sync complete: %d users, %d synced, %d discrepancies, %d errors",
        stats["total_users"],
        stats["synced"],
        stats["discrepancies"],
        stats["errors"],
    )
    return stats


@celery_app.task(name="app.tasks.calculate_staking_rewards")
def calculate_staking_rewards() -> dict:
    """Calculate and distribute daily staking rewards.

    Iterates all active staking positions and calculates
    accrued rewards based on 5% APY.

    Returns:
        Dict with distribution results.
    """
    logger.info("Running staking rewards calculation task")
    # Would iterate StakingPosition records and update pending_rewards
    return {"positions_updated": 0, "total_rewards": "0"}


@celery_app.task(bind=True, name="app.tasks.send_notification")
def send_notification(self, user_id: str, title: str, body: str) -> dict:
    """Send a push notification to a user.

    Args:
        user_id: Target user UUID.
        title: Notification title.
        body: Notification body text.

    Returns:
        Dict with delivery status.
    """
    logger.info("Sending notification to user %s: %s", user_id, title)
    # Would integrate with FCM/APNS for push notifications
    return {"user_id": user_id, "sent": True}


@celery_app.task(name="app.tasks.deliver_webhook")
def deliver_webhook(webhook_id: int, event_type: str, payload: dict) -> dict:
    """Deliver a webhook notification asynchronously.

    Looks up the webhook by ID, POSTs the payload to its URL with an
    HMAC-SHA256 signature, and updates the webhook record with the result.

    Args:
        webhook_id: The AuthorityWebhook ID to deliver to.
        event_type: The event type string (e.g. "report.verified").
        payload: The JSON-serialisable event payload.

    Returns:
        Dict with delivery result (success, status_code, etc.).
    """
    logger.info(
        "Delivering webhook %d for event %s", webhook_id, event_type
    )
    return _run_async(_deliver_webhook_async(webhook_id, event_type, payload))


async def _deliver_webhook_async(
    webhook_id: int, event_type: str, payload: dict
) -> dict:
    """Async implementation of the webhook delivery task."""
    from sqlalchemy import select as sa_select

    from app.core.database import async_session_maker
    from app.models.webhook import AuthorityWebhook
    from app.services.webhook import WebhookService

    async with async_session_maker() as session:
        result = await session.execute(
            sa_select(AuthorityWebhook).where(AuthorityWebhook.id == webhook_id)
        )
        webhook = result.scalar_one_or_none()
        if not webhook:
            logger.warning("Webhook %d not found; skipping delivery", webhook_id)
            return {"webhook_id": webhook_id, "success": False, "error": "not_found"}

        svc = WebhookService(session)
        outcome = await svc._deliver(webhook, event_type, payload)
        return outcome


@celery_app.task(name="app.tasks.seed_catalogues")
def seed_catalogues() -> dict:
    """Seed catalogue tables (idempotent).

    Populates infractions, vehicle types, levels, and badges.
    Safe to run multiple times -- uses INSERT ... ON CONFLICT DO UPDATE.

    Returns:
        Dict with row counts per table.
    """
    logger.info("Running catalogue seed task")
    return _run_async(_seed_catalogues_async())


async def _seed_catalogues_async() -> dict:
    """Async implementation of the catalogue seed task."""
    from app.scripts.seed_catalogues import seed_catalogues as _do_seed

    results = await _do_seed()
    # Convert to plain dict for JSON serialisation
    return {k: v for k, v in results.items()}


@celery_app.task(bind=True, name="app.tasks.process_evidence")
def process_evidence(self, report_id: str, evidence_url: str) -> dict:
    """Process uploaded evidence (thumbnail generation, IPFS upload).

    Args:
        report_id: The report UUID.
        evidence_url: URL of the uploaded evidence file.

    Returns:
        Dict with processing results.
    """
    logger.info("Processing evidence for report %s", report_id)
    # Would generate thumbnails, upload to IPFS, update evidence record
    return {"report_id": report_id, "processed": True}
