"""OAuth 2.0 Authorization Code provider endpoints.

Multando acts as an OAuth 2.0 authorization server so that third-party apps
(e.g. ZPP) that already hold an API key can implement "Connect Multando"
without requiring users to double-login.

Flow:
1. Third-party redirects user to GET /oauth/authorize  (returns consent info)
2. Frontend renders consent screen, user authorizes
3. Frontend POSTs to POST /oauth/authorize  (creates auth code, returns redirect URL)
4. Third-party exchanges code via POST /oauth/token
5. Third-party calls GET /oauth/userinfo with the access token
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.api_key import ApiKey
from app.models.oauth import OAuthAuthorizationCode
from app.schemas.oauth import (
    OAuthAuthorizeResponse,
    OAuthConsentInfo,
    OAuthTokenRequest,
    OAuthTokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth-provider"])

# Allowed scopes that can be requested by third-party apps
ALLOWED_SCOPES = {
    "reports:create",
    "reports:read",
    "balance:read",
    "profile:read",
}

REFRESH_TOKEN_EXPIRE_DAYS = 30


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _validate_client(
    db: AsyncSession,
    client_id: str,
) -> ApiKey:
    """Look up and validate the API key used as OAuth client_id.

    The third-party passes its full API key as client_id (they already
    have it).  We validate by hashing and comparing, reusing the
    ApiKeyService logic.
    """
    from app.services.api_key import ApiKeyService

    api_key_service = ApiKeyService(db)
    api_key = await api_key_service.validate_key(client_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or inactive client_id (API key)",
        )
    return api_key


def _validate_scopes(requested: str, api_key: ApiKey) -> list[str]:
    """Validate that requested scopes are allowed and within the API key's scope."""
    scopes = [s.strip() for s in requested.split(",") if s.strip()]
    if not scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one scope is required",
        )

    # Check against global allowed scopes
    invalid = set(scopes) - ALLOWED_SCOPES
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scopes: {', '.join(sorted(invalid))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_SCOPES))}",
        )

    # If the API key has restricted scopes, enforce them
    if api_key.scopes:
        key_scopes = set(api_key.scopes)
        over = set(scopes) - key_scopes
        if over:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scopes exceed API key permissions: {', '.join(sorted(over))}",
            )

    return scopes


def _build_redirect_url(redirect_uri: str, code: str, state: str | None) -> str:
    """Append code and state query params to the redirect URI."""
    parsed = urlparse(redirect_uri)
    params = parse_qs(parsed.query)
    params["code"] = [code]
    if state:
        params["state"] = [state]
    # Flatten single-value lists for urlencode
    flat = {k: v[0] if len(v) == 1 else v for k, v in params.items()}
    new_query = urlencode(flat, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get(
    "/authorize",
    response_model=OAuthConsentInfo,
    summary="Get consent screen info",
    description="Validate the OAuth request and return info for the consent screen.",
)
async def authorize_get(
    db: DbSession,
    client_id: str = Query(..., description="Third-party API key"),
    redirect_uri: str = Query(..., description="Where to redirect after consent"),
    scope: str = Query(..., description="Comma-separated scopes"),
    state: str | None = Query(default=None, description="CSRF state value"),
    response_type: str = Query(default="code", description="Must be 'code'"),
) -> OAuthConsentInfo:
    """Return consent screen information for the frontend to render.

    Validates client_id, scopes, and response_type without requiring
    the user to be logged in yet (the frontend will authenticate the
    user separately before calling POST /oauth/authorize).
    """
    if response_type != "code":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only response_type=code is supported",
        )

    api_key = await _validate_client(db, client_id)
    scopes = _validate_scopes(scope, api_key)

    return OAuthConsentInfo(
        client_name=api_key.name,
        scopes=scopes,
    )


@router.post(
    "/authorize",
    response_model=OAuthAuthorizeResponse,
    summary="Authorize and generate code",
    description="User consents; generates a short-lived authorization code.",
)
async def authorize_post(
    db: DbSession,
    current_user: CurrentUser,
    client_id: str = Query(..., description="Third-party API key"),
    redirect_uri: str = Query(..., description="Redirect URI"),
    scope: str = Query(..., description="Comma-separated scopes"),
    state: str | None = Query(default=None, description="CSRF state value"),
) -> OAuthAuthorizeResponse:
    """Generate an authorization code after the user consents.

    The user must be logged in (Bearer token required). The frontend
    calls this after the user clicks "Authorize" on the consent screen.
    """
    api_key = await _validate_client(db, client_id)
    scopes = _validate_scopes(scope, api_key)

    # Generate a cryptographically random authorization code
    code = secrets.token_hex(32)  # 64 hex chars
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.OAUTH_CODE_EXPIRE_MINUTES
    )

    auth_code = OAuthAuthorizationCode(
        code=code,
        client_id=client_id,
        user_id=current_user.id,
        redirect_uri=redirect_uri,
        scope=",".join(scopes),
        state=state,
        expires_at=expires_at,
        used=False,
    )
    db.add(auth_code)
    await db.flush()

    redirect_url = _build_redirect_url(redirect_uri, code, state)
    return OAuthAuthorizeResponse(redirect_url=redirect_url)


@router.post(
    "/token",
    response_model=OAuthTokenResponse,
    summary="Exchange code or refresh token for access token",
    description="Standard OAuth 2.0 token endpoint.",
)
async def token(
    body: OAuthTokenRequest,
    db: DbSession,
) -> OAuthTokenResponse:
    """Exchange an authorization code or refresh token for an access token.

    Supports two grant types:
    - **authorization_code**: exchange a one-time code for tokens
    - **refresh_token**: exchange a refresh token for a fresh token pair
    """
    if body.grant_type == "authorization_code":
        return await _handle_authorization_code(body, db)
    elif body.grant_type == "refresh_token":
        return await _handle_refresh_token(body, db)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported grant_type. Use 'authorization_code' or 'refresh_token'.",
        )


@router.get(
    "/userinfo",
    summary="Get user info for the token holder",
    description="OpenID Connect-style userinfo endpoint.",
)
async def userinfo(current_user: CurrentUser) -> dict:
    """Return basic user info for the authenticated token holder.

    This is the standard OpenID Connect userinfo endpoint that
    third-party apps call after obtaining an access token.
    """
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "display_name": current_user.display_name or current_user.username or "",
        "avatar_url": current_user.avatar_url,
    }


# ------------------------------------------------------------------
# Grant type handlers
# ------------------------------------------------------------------


async def _handle_authorization_code(
    body: OAuthTokenRequest,
    db: AsyncSession,
) -> OAuthTokenResponse:
    """Handle the authorization_code grant type."""
    if not body.code or not body.client_id or not body.redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code, client_id, and redirect_uri are required for authorization_code grant",
        )

    # Look up the authorization code
    result = await db.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == body.code
        )
    )
    auth_code = result.scalar_one_or_none()

    if not auth_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid authorization code",
        )

    # Verify the code has not been used
    if auth_code.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code has already been used",
        )

    # Verify the code has not expired
    if datetime.now(timezone.utc) > auth_code.expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code has expired",
        )

    # Verify client_id matches
    if auth_code.client_id != body.client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id does not match the authorization code",
        )

    # Verify redirect_uri matches
    if auth_code.redirect_uri != body.redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redirect_uri does not match the authorization code",
        )

    # Mark code as used
    auth_code.used = True
    await db.flush()

    # Create scoped access token
    scope = auth_code.scope
    access_token = create_access_token(
        subject=str(auth_code.user_id),
        expires_delta=timedelta(minutes=settings.OAUTH_ACCESS_TOKEN_EXPIRE_MINUTES),
        additional_claims={
            "scope": scope,
            "type": "oauth",
            "client_id": body.client_id,
        },
    )

    # Create refresh token (longer lived)
    refresh_token = create_access_token(
        subject=str(auth_code.user_id),
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        additional_claims={
            "type": "oauth_refresh",
            "scope": scope,
            "client_id": body.client_id,
        },
    )

    return OAuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.OAUTH_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        scope=scope,
    )


async def _handle_refresh_token(
    body: OAuthTokenRequest,
    db: AsyncSession,
) -> OAuthTokenResponse:
    """Handle the refresh_token grant type."""
    if not body.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="refresh_token is required for refresh_token grant",
        )

    # Decode the refresh token
    token_data = decode_access_token(body.refresh_token)
    if token_data is None or token_data.sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # Decode full payload to extract claims
    from jose import jwt as jose_jwt

    payload = jose_jwt.decode(
        body.refresh_token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    if payload.get("type") != "oauth_refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is not an OAuth refresh token",
        )

    scope = payload.get("scope", "")
    client_id = payload.get("client_id", "")
    user_id = token_data.sub

    # Verify user still exists
    from app.services.auth import AuthService
    from uuid import UUID

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Issue new token pair
    access_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=settings.OAUTH_ACCESS_TOKEN_EXPIRE_MINUTES),
        additional_claims={
            "scope": scope,
            "type": "oauth",
            "client_id": client_id,
        },
    )

    refresh_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        additional_claims={
            "type": "oauth_refresh",
            "scope": scope,
            "client_id": client_id,
        },
    )

    return OAuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.OAUTH_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        scope=scope,
    )
