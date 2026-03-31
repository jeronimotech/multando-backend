"""Webhook service for managing authority webhook subscriptions and delivery."""

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.authority import Authority
from app.models.webhook import AuthorityWebhook

logger = logging.getLogger(__name__)

MAX_FAILURE_COUNT = 10
WEBHOOK_TIMEOUT_SECONDS = 10


class WebhookService:
    """Service for authority webhook CRUD and delivery."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_webhook(
        self,
        authority_id: int,
        url: str,
        events: list[str],
        secret: str | None = None,
    ) -> AuthorityWebhook:
        """Create a new webhook for an authority.

        Args:
            authority_id: The authority that owns the webhook.
            url: HTTPS URL to POST to.
            events: List of event types to subscribe to.
            secret: Optional HMAC secret. Auto-generated if omitted.

        Returns:
            The created AuthorityWebhook.
        """
        if not secret:
            secret = secrets.token_urlsafe(32)

        webhook = AuthorityWebhook(
            authority_id=authority_id,
            url=url,
            secret=secret,
            events=events,
            is_active=True,
            failure_count=0,
        )
        self.db.add(webhook)
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def list_webhooks(self, authority_id: int) -> list[AuthorityWebhook]:
        """List all webhooks belonging to an authority.

        Args:
            authority_id: The authority whose webhooks to list.

        Returns:
            List of AuthorityWebhook objects.
        """
        result = await self.db.execute(
            select(AuthorityWebhook)
            .where(AuthorityWebhook.authority_id == authority_id)
            .order_by(AuthorityWebhook.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_webhook(
        self, authority_id: int, webhook_id: int
    ) -> AuthorityWebhook | None:
        """Get a single webhook ensuring it belongs to the authority."""
        result = await self.db.execute(
            select(AuthorityWebhook).where(
                AuthorityWebhook.id == webhook_id,
                AuthorityWebhook.authority_id == authority_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_webhook(
        self,
        authority_id: int,
        webhook_id: int,
        url: str | None = None,
        events: list[str] | None = None,
        is_active: bool | None = None,
    ) -> AuthorityWebhook | None:
        """Update a webhook's configuration.

        Args:
            authority_id: The owning authority.
            webhook_id: The webhook to update.
            url: New URL (optional).
            events: New event list (optional).
            is_active: New active status (optional).

        Returns:
            Updated AuthorityWebhook, or None if not found.
        """
        webhook = await self.get_webhook(authority_id, webhook_id)
        if not webhook:
            return None

        if url is not None:
            webhook.url = url
        if events is not None:
            webhook.events = events
        if is_active is not None:
            webhook.is_active = is_active
            # Reset failure count when re-enabling
            if is_active:
                webhook.failure_count = 0

        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def delete_webhook(self, authority_id: int, webhook_id: int) -> bool:
        """Delete a webhook. Returns True if deleted.

        Args:
            authority_id: The owning authority.
            webhook_id: The webhook to delete.

        Returns:
            True if successfully deleted, False if not found.
        """
        webhook = await self.get_webhook(authority_id, webhook_id)
        if not webhook:
            return False
        await self.db.delete(webhook)
        await self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    async def trigger_webhooks(
        self, city_id: int, event_type: str, payload: dict
    ) -> list[dict]:
        """Fire webhooks for all authorities in a given city that subscribe to the event.

        For each matching active webhook:
        - POST the JSON payload with an X-Multando-Signature HMAC-SHA256 header.
        - Track success/failure and update the webhook record.
        - Disable the webhook after MAX_FAILURE_COUNT consecutive failures.

        Args:
            city_id: The city where the event occurred.
            event_type: The event type (e.g. "report.created").
            payload: The JSON-serialisable payload to POST.

        Returns:
            List of result dicts with webhook_id, success, and status_code.
        """
        # Find all active webhooks for authorities whose city matches
        q = (
            select(AuthorityWebhook)
            .join(Authority, AuthorityWebhook.authority_id == Authority.id)
            .where(
                Authority.city_id == city_id,
                AuthorityWebhook.is_active.is_(True),
            )
        )
        result = await self.db.execute(q)
        webhooks = list(result.scalars().all())

        results = []
        for webhook in webhooks:
            if event_type not in webhook.events:
                continue
            outcome = await self._deliver(webhook, event_type, payload)
            results.append(outcome)

        return results

    async def test_webhook(
        self, authority_id: int, webhook_id: int
    ) -> dict:
        """Send a test ping to verify the webhook URL works.

        Args:
            authority_id: The owning authority.
            webhook_id: The webhook to test.

        Returns:
            Dict with success, status_code, response_time_ms, and optional error.

        Raises:
            ValueError: If the webhook is not found.
        """
        webhook = await self.get_webhook(authority_id, webhook_id)
        if not webhook:
            raise ValueError("Webhook not found")

        test_payload = {
            "event": "webhook.test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"message": "This is a test ping from Multando."},
        }

        return await self._deliver(webhook, "webhook.test", test_payload, is_test=True)

    async def _deliver(
        self,
        webhook: AuthorityWebhook,
        event_type: str,
        payload: dict,
        is_test: bool = False,
    ) -> dict:
        """Perform the actual HTTP POST to a webhook URL.

        Args:
            webhook: The webhook to deliver to.
            event_type: The event type string.
            payload: The JSON payload.
            is_test: If True, don't update failure counts.

        Returns:
            Dict with webhook_id, success, status_code, response_time_ms, error.
        """
        body = json.dumps(
            {"event": event_type, "data": payload},
            default=str,
        )
        signature = hmac.new(
            webhook.secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Multando-Signature": f"sha256={signature}",
            "X-Multando-Event": event_type,
        }

        start = time.monotonic()
        status_code = None
        error_msg = None
        success = False

        try:
            async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
                response = await client.post(webhook.url, content=body, headers=headers)
                status_code = response.status_code
                success = 200 <= status_code < 300
        except httpx.TimeoutException:
            error_msg = "Request timed out"
        except httpx.RequestError as exc:
            error_msg = f"Request error: {exc}"
        except Exception as exc:
            error_msg = f"Unexpected error: {exc}"

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)

        # Update webhook record (skip for test pings to keep stats clean)
        if not is_test:
            webhook.last_triggered_at = datetime.now(timezone.utc)
            webhook.last_status_code = status_code

            if success:
                webhook.failure_count = 0
            else:
                webhook.failure_count += 1
                if webhook.failure_count >= MAX_FAILURE_COUNT:
                    webhook.is_active = False
                    logger.warning(
                        "Webhook %d disabled after %d consecutive failures",
                        webhook.id,
                        webhook.failure_count,
                    )

            await self.db.commit()

        return {
            "webhook_id": webhook.id,
            "success": success,
            "status_code": status_code,
            "response_time_ms": elapsed_ms,
            "error": error_msg,
        }
