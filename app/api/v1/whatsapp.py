"""WhatsApp webhook endpoints.

Provides the GET (verification) and POST (incoming messages) endpoints
required by Meta's WhatsApp Cloud API.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import settings
from app.services.whatsapp.client import WhatsAppClient
from app.services.whatsapp.signature import verify_webhook_signature
from app.services.whatsapp.webhook import handle_incoming

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

# Shared WhatsApp client (lazily initialized)
_whatsapp_client: WhatsAppClient | None = None


def _get_whatsapp_client() -> WhatsAppClient:
    """Lazy-initialize the WhatsApp client singleton."""
    global _whatsapp_client
    if _whatsapp_client is None:
        _whatsapp_client = WhatsAppClient()
    return _whatsapp_client


# ------------------------------------------------------------------
# GET /whatsapp/webhook - Verification (Meta sends a challenge)
# ------------------------------------------------------------------


@router.get(
    "/webhook",
    summary="WhatsApp webhook verification",
    description="Called by Meta during webhook setup to verify the endpoint.",
)
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
) -> int:
    """Verify webhook for WhatsApp Cloud API setup.

    Returns the challenge value as an integer if verification succeeds.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("WhatsApp webhook verification successful")
        return int(hub_challenge)

    logger.warning(
        "WhatsApp webhook verification failed: mode=%s, token_match=%s",
        hub_mode,
        hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN,
    )
    raise HTTPException(status_code=403, detail="Verification failed")


# ------------------------------------------------------------------
# POST /whatsapp/webhook - Receive incoming messages
# ------------------------------------------------------------------


@router.post(
    "/webhook",
    summary="WhatsApp webhook receiver",
    description="Receives incoming WhatsApp messages and status updates from Meta.",
)
async def handle_webhook(request: Request) -> dict[str, str]:
    """Handle incoming WhatsApp webhook events.

    1. Verify signature (skipped in dev when WHATSAPP_APP_SECRET is empty).
    2. Parse the webhook payload.
    3. Route messages to the shared chatbot engine via the webhook handler.
    """
    await verify_webhook_signature(request)

    try:
        body = await request.json()
    except Exception as exc:
        logger.error("Failed to parse WhatsApp webhook body: %s", exc)
        return {"status": "error", "message": "Invalid JSON"}

    logger.debug("WhatsApp webhook received: %s", body)

    whatsapp = _get_whatsapp_client()
    await handle_incoming(body, whatsapp)

    return {"status": "ok"}
