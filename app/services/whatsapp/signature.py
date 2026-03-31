"""WhatsApp webhook signature verification.

Uses HMAC-SHA256 with the WhatsApp app secret to verify
that incoming webhook requests came from Meta's servers.
"""

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_webhook_signature(request: Request) -> None:
    """Verify the X-Hub-Signature-256 header on webhook POST requests.

    Skip verification if WHATSAPP_APP_SECRET is empty (dev mode).

    Args:
        request: The incoming FastAPI request.

    Raises:
        HTTPException: 403 if signature is invalid or missing.
    """
    if not settings.WHATSAPP_APP_SECRET:
        return  # Dev mode - skip verification

    signature_header = request.headers.get("X-Hub-Signature-256", "")
    if not signature_header.startswith("sha256="):
        logger.warning("Missing or malformed X-Hub-Signature-256 header")
        raise HTTPException(status_code=403, detail="Invalid signature")

    expected_signature = signature_header[7:]  # Remove "sha256=" prefix

    body = await request.body()
    computed = hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, expected_signature):
        logger.warning("Webhook signature mismatch")
        raise HTTPException(status_code=403, detail="Invalid signature")
