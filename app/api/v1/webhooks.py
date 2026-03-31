"""Authority webhook management endpoints.

All endpoints require the current user to hold an ADMIN role within their
authority (via the AuthorityAdmin dependency).
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthorityAdmin, DbSession
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookCreatedResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookTestResponse,
    WebhookUpdateRequest,
)
from app.services.webhook import WebhookService

router = APIRouter(prefix="/authority-mgmt/webhooks", tags=["authority-mgmt"])


@router.post(
    "/",
    response_model=WebhookCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook for my authority",
)
async def create_webhook(
    body: WebhookCreateRequest,
    auth: AuthorityAdmin,
    db: DbSession,
) -> WebhookCreatedResponse:
    _, authority = auth
    svc = WebhookService(db)
    webhook = await svc.create_webhook(
        authority_id=authority.id,
        url=body.url,
        events=body.events,
        secret=body.secret,
    )
    return WebhookCreatedResponse(
        id=webhook.id,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        secret=webhook.secret,
        created_at=webhook.created_at,
    )


@router.get(
    "/",
    response_model=WebhookListResponse,
    summary="List webhooks for my authority",
)
async def list_webhooks(
    auth: AuthorityAdmin,
    db: DbSession,
) -> WebhookListResponse:
    _, authority = auth
    svc = WebhookService(db)
    webhooks = await svc.list_webhooks(authority.id)
    items = [
        WebhookResponse(
            id=w.id,
            url=w.url,
            events=w.events,
            is_active=w.is_active,
            last_triggered_at=w.last_triggered_at,
            last_status_code=w.last_status_code,
            failure_count=w.failure_count,
            created_at=w.created_at,
        )
        for w in webhooks
    ]
    return WebhookListResponse(items=items, total=len(items))


@router.put(
    "/{webhook_id}",
    response_model=WebhookResponse,
    summary="Update a webhook",
)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdateRequest,
    auth: AuthorityAdmin,
    db: DbSession,
) -> WebhookResponse:
    _, authority = auth
    svc = WebhookService(db)
    updates = body.model_dump(exclude_unset=True)
    webhook = await svc.update_webhook(authority.id, webhook_id, **updates)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return WebhookResponse(
        id=webhook.id,
        url=webhook.url,
        events=webhook.events,
        is_active=webhook.is_active,
        last_triggered_at=webhook.last_triggered_at,
        last_status_code=webhook.last_status_code,
        failure_count=webhook.failure_count,
        created_at=webhook.created_at,
    )


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a webhook",
)
async def delete_webhook(
    webhook_id: int,
    auth: AuthorityAdmin,
    db: DbSession,
) -> dict:
    _, authority = auth
    svc = WebhookService(db)
    deleted = await svc.delete_webhook(authority.id, webhook_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return {"detail": "Webhook deleted"}


@router.post(
    "/{webhook_id}/test",
    response_model=WebhookTestResponse,
    summary="Send a test ping to a webhook",
)
async def test_webhook(
    webhook_id: int,
    auth: AuthorityAdmin,
    db: DbSession,
) -> WebhookTestResponse:
    _, authority = auth
    svc = WebhookService(db)
    try:
        result = await svc.test_webhook(authority.id, webhook_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )
    return WebhookTestResponse(
        success=result["success"],
        status_code=result.get("status_code"),
        response_time_ms=result.get("response_time_ms"),
        error=result.get("error"),
    )
