"""Federation API endpoints.

Hub-side endpoints for receiving synced data from self-hosted instances,
plus admin endpoints for managing registered instances.
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, DbSession
from app.schemas.federation import (
    FederationInstanceListItem,
    FederationInstanceRegister,
    FederationInstanceResponse,
    FederationStatsResponse,
    FederationSyncRequest,
    FederationSyncResponse,
)
from app.services.federation import FederationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/federation", tags=["federation"])


# ---------------------------------------------------------------------------
# Public (key-authenticated via X-Federation-Key header)
# ---------------------------------------------------------------------------


@router.post(
    "/sync",
    response_model=FederationSyncResponse,
    summary="Receive sync from a federated instance",
)
async def receive_sync(
    body: FederationSyncRequest,
    db: DbSession,
    x_federation_key: str = Header(..., alias="X-Federation-Key"),
) -> FederationSyncResponse:
    """Receive anonymized report data from a self-hosted instance."""
    svc = FederationService(db)

    # Validate the instance credentials
    is_valid = await svc.validate_instance(body.instance_id, x_federation_key)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid instance credentials",
        )

    count = await svc.receive_sync(body.instance_id, body.items)
    await db.commit()

    return FederationSyncResponse(
        received_count=count,
        instance_id=body.instance_id,
    )


@router.get(
    "/stats",
    response_model=FederationStatsResponse,
    summary="Public aggregated federation statistics",
)
async def get_federation_stats(db: DbSession) -> FederationStatsResponse:
    """Return aggregate stats across all federated instances."""
    svc = FederationService(db)
    return await svc.get_federation_stats()


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/instances",
    response_model=FederationInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new federation instance",
)
async def register_instance(
    body: FederationInstanceRegister,
    db: DbSession,
    _admin: AdminUser = None,
) -> FederationInstanceResponse:
    """Register a new self-hosted instance (admin only). Returns API key once."""
    svc = FederationService(db)
    result = await svc.register_instance(body)
    await db.commit()
    return result


@router.get(
    "/instances",
    response_model=list[FederationInstanceListItem],
    summary="List registered federation instances",
)
async def list_instances(
    db: DbSession,
    _admin: AdminUser = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[FederationInstanceListItem]:
    """List all registered federation instances (admin only)."""
    svc = FederationService(db)
    items, _total = await svc.list_instances(page, page_size)
    return items


@router.delete(
    "/instances/{instance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a federation instance",
)
async def deactivate_instance(
    instance_id: str,
    db: DbSession,
    _admin: AdminUser = None,
) -> None:
    """Deactivate a federation instance (admin only)."""
    svc = FederationService(db)
    success = await svc.deactivate_instance(instance_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instance not found",
        )
    await db.commit()
