"""OAuth social login endpoints for Google and GitHub.

This module provides endpoints for authenticating users via third-party
OAuth providers. When a user authenticates via OAuth, they are either
matched to an existing account by email or a new account is created.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.core.config import settings
from app.core.security import create_access_token
from app.models import Level, User, UserBadge
from app.schemas.auth import TokenResponse
from app.schemas.oauth import OAuthCodeRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["oauth"])

# Refresh token expiration (7 days)
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _create_tokens(user_id: str) -> TokenResponse:
    """Create access and refresh tokens for a user."""
    access_token = create_access_token(subject=user_id)
    refresh_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        additional_claims={"type": "refresh"},
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def _get_or_create_oauth_user(
    db: AsyncSession,
    *,
    email: str,
    display_name: str,
    avatar_url: str | None = None,
) -> User:
    """Find an existing user by email or create a new one for OAuth login.

    If a user with the given email already exists, their last_login_at is
    updated and the existing account is returned (account linking).

    If no user exists, a new account is created with a generated username,
    no password (OAuth-only), and a custodial wallet.

    Args:
        db: Async database session.
        email: Verified email from the OAuth provider.
        display_name: Name from the OAuth provider profile.
        avatar_url: Avatar/profile picture URL from the provider.

    Returns:
        The existing or newly created User.
    """
    # Check for existing user
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.level),
            selectinload(User.badges).selectinload(UserBadge.badge),
        )
        .where(User.email == email)
    )
    user = result.scalar_one_or_none()

    if user:
        # Existing user: update last login, optionally fill missing avatar
        user.last_login_at = datetime.now(timezone.utc)
        if not user.avatar_url and avatar_url:
            user.avatar_url = avatar_url
        await db.flush()
        return user

    # New user: create account
    # Generate a unique username from the email prefix
    base_username = email.split("@")[0].lower()
    # Strip non-alphanumeric except underscores, ensure length
    clean_username = "".join(c for c in base_username if c.isalnum() or c == "_")
    if len(clean_username) < 3:
        clean_username = clean_username + secrets.token_hex(3)

    # Ensure uniqueness by appending random suffix if needed
    username = clean_username[:30]
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        username = f"{clean_username[:24]}_{secrets.token_hex(3)}"

    # Get default level (tier 1)
    level_result = await db.execute(select(Level).where(Level.tier == 1))
    default_level = level_result.scalar_one_or_none()

    user = User(
        email=email,
        username=username,
        password_hash=None,  # OAuth users have no password
        display_name=display_name or username,
        avatar_url=avatar_url,
        locale="en",
        level_id=default_level.id if default_level else None,
        is_active=True,
        is_verified=True,  # Email verified by OAuth provider
        last_login_at=datetime.now(timezone.utc),
    )

    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Auto-provision custodial wallet
    from app.services.wallet import WalletService

    wallet_service = WalletService(db)
    await wallet_service.create_custodial_wallet(user.id)

    # Reload with relationships
    result = await db.execute(
        select(User)
        .options(
            selectinload(User.level),
            selectinload(User.badges).selectinload(UserBadge.badge),
        )
        .where(User.id == user.id)
    )
    return result.scalar_one()


async def _exchange_google_code(code: str, redirect_uri: str) -> dict:
    """Exchange a Google authorization code for user info.

    Args:
        code: The authorization code from Google OAuth consent screen.
        redirect_uri: The redirect URI used in the original authorization request.

    Returns:
        Dict with keys: email, name, picture.

    Raises:
        HTTPException: If the token exchange or user info request fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Exchange authorization code for tokens
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )

        if token_resp.status_code != 200:
            logger.error("Google token exchange failed: %s", token_resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate with Google",
            )

        tokens = token_resp.json()
        access_token = tokens.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No access token received from Google",
            )

        # Get user info using the access token
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if userinfo_resp.status_code != 200:
            logger.error("Google userinfo request failed: %s", userinfo_resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to retrieve Google user info",
            )

        userinfo = userinfo_resp.json()
        email = userinfo.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account does not have an email address",
            )

        return {
            "email": email,
            "name": userinfo.get("name", ""),
            "picture": userinfo.get("picture"),
        }


async def _exchange_github_code(code: str, redirect_uri: str) -> dict:
    """Exchange a GitHub authorization code for user info.

    Args:
        code: The authorization code from GitHub OAuth.
        redirect_uri: The redirect URI (passed to token exchange for validation).

    Returns:
        Dict with keys: email, name, avatar_url.

    Raises:
        HTTPException: If the token exchange or user info request fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Exchange code for access token
        token_payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        }
        if redirect_uri:
            token_payload["redirect_uri"] = redirect_uri

        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            json=token_payload,
            headers={"Accept": "application/json"},
        )

        if token_resp.status_code != 200:
            logger.error("GitHub token exchange failed: %s", token_resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to authenticate with GitHub",
            )

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            error = token_data.get("error_description", "Unknown error")
            logger.error("GitHub token exchange error: %s", error)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"GitHub authentication failed: {error}",
            )

        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        # Get user profile
        user_resp = await client.get(
            "https://api.github.com/user",
            headers=auth_headers,
        )

        if user_resp.status_code != 200:
            logger.error("GitHub user request failed: %s", user_resp.text)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Failed to retrieve GitHub user info",
            )

        user_data = user_resp.json()

        # Get primary verified email (may not be public on the profile)
        email = user_data.get("email")
        if not email:
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers=auth_headers,
            )

            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                # Prefer primary + verified email
                primary = next(
                    (e for e in emails if e.get("primary") and e.get("verified")),
                    None,
                )
                if not primary:
                    # Fall back to any verified email
                    primary = next(
                        (e for e in emails if e.get("verified")),
                        None,
                    )
                if primary:
                    email = primary["email"]

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not retrieve a verified email from your GitHub account. "
                "Please ensure you have a verified email on GitHub.",
            )

        return {
            "email": email,
            "name": user_data.get("name") or user_data.get("login", ""),
            "avatar_url": user_data.get("avatar_url"),
        }


@router.post(
    "/google",
    response_model=TokenResponse,
    summary="Login with Google",
    description="Authenticate using a Google OAuth authorization code. "
    "Creates a new account if the email is not already registered.",
)
async def google_login(body: OAuthCodeRequest, db: DbSession) -> TokenResponse:
    """Authenticate a user via Google OAuth.

    The frontend redirects the user to Google's consent screen, which returns
    an authorization code. This endpoint exchanges that code for user info
    and returns JWT tokens.

    Args:
        body: Request containing the Google authorization code and redirect_uri.
        db: Database session.

    Returns:
        TokenResponse with access and refresh tokens.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )

    google_user = await _exchange_google_code(body.code, body.redirect_uri)

    user = await _get_or_create_oauth_user(
        db,
        email=google_user["email"],
        display_name=google_user["name"],
        avatar_url=google_user.get("picture"),
    )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return _create_tokens(str(user.id))


@router.post(
    "/github",
    response_model=TokenResponse,
    summary="Login with GitHub",
    description="Authenticate using a GitHub OAuth authorization code. "
    "Creates a new account if the email is not already registered.",
)
async def github_login(body: OAuthCodeRequest, db: DbSession) -> TokenResponse:
    """Authenticate a user via GitHub OAuth.

    The frontend redirects the user to GitHub's authorization page, which
    returns an authorization code. This endpoint exchanges that code for
    user info and returns JWT tokens.

    Args:
        body: Request containing the GitHub authorization code and redirect_uri.
        db: Database session.

    Returns:
        TokenResponse with access and refresh tokens.
    """
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured",
        )

    github_user = await _exchange_github_code(body.code, body.redirect_uri)

    user = await _get_or_create_oauth_user(
        db,
        email=github_user["email"],
        display_name=github_user["name"],
        avatar_url=github_user.get("avatar_url"),
    )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return _create_tokens(str(user.id))
