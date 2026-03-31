"""API key management endpoints.

Allows authenticated users to create, list, and revoke/delete API keys
for use with Multando SDKs.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.schemas.api_key import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
)
from app.services.api_key import ApiKeyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreateResponse:
    """Create a new API key for the authenticated user.

    The full key value is returned ONLY in this response and cannot be
    retrieved again. Store it securely.

    Args:
        body: API key creation parameters.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        ApiKeyCreateResponse including the full key (shown once).
    """
    service = ApiKeyService(db)
    try:
        api_key, raw_key = await service.create_key(
            user_id=current_user.id,
            name=body.name,
            environment=body.environment,
            scopes=body.scopes,
            rate_limit=body.rate_limit,
            expires_in_days=body.expires_in_days,
        )
        return ApiKeyCreateResponse(
            id=api_key.id,
            key=raw_key,
            key_prefix=api_key.key_prefix,
            name=api_key.name,
            scopes=api_key.scopes or [],
            rate_limit=api_key.rate_limit,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
        )
    except Exception:
        logger.exception("Failed to create API key for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API key",
        )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyListResponse:
    """List all API keys for the authenticated user.

    Returns key prefixes only (never the full key).

    Args:
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        ApiKeyListResponse with key metadata.
    """
    service = ApiKeyService(db)
    try:
        items, total = await service.list_keys(current_user.id)
        return ApiKeyListResponse(
            items=[
                ApiKeyResponse(
                    id=k.id,
                    key_prefix=k.key_prefix,
                    name=k.name,
                    is_active=k.is_active,
                    scopes=k.scopes or [],
                    rate_limit=k.rate_limit,
                    last_used_at=k.last_used_at,
                    created_at=k.created_at,
                    expires_at=k.expires_at,
                )
                for k in items
            ],
            total=total,
        )
    except Exception:
        logger.exception("Failed to list API keys for user %s", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list API keys",
        )


@router.delete("/{key_id}", status_code=status.HTTP_200_OK)
async def delete_api_key(
    key_id: int,
    current_user: CurrentUser,
    revoke_only: bool = Query(
        default=False,
        description="If true, revoke (deactivate) instead of hard-deleting",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke or delete an API key.

    By default, hard-deletes the key. Pass `?revoke_only=true` to
    deactivate without deleting.

    Args:
        key_id: ID of the API key.
        current_user: The authenticated user.
        revoke_only: If True, only deactivate the key.
        db: Async database session.

    Returns:
        Status message.
    """
    service = ApiKeyService(db)
    try:
        if revoke_only:
            result = await service.revoke_key(current_user.id, key_id)
            if result is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found",
                )
            return {"status": "revoked", "key_id": str(key_id)}
        else:
            deleted = await service.delete_key(current_user.id, key_id)
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="API key not found",
                )
            return {"status": "deleted", "key_id": str(key_id)}
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Failed to delete/revoke API key %s for user %s",
            key_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete API key",
        )
