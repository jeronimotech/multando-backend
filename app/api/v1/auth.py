"""Authentication endpoints for the Multando API.

This module provides endpoints for user registration, login, token management,
and wallet linking.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.security import create_access_token
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    WalletLinkRequest,
)
from app.schemas.badge import BadgeResponse, UserBadgeResponse
from app.schemas.common import MessageResponse
from app.schemas.level import LevelResponse
from app.schemas.user import UserProfile, UserRole
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# Refresh token expiration (7 days)
REFRESH_TOKEN_EXPIRE_DAYS = 7


def _build_user_profile(user) -> UserProfile:
    """Build a UserProfile response from a User model.

    Args:
        user: The User model instance.

    Returns:
        UserProfile schema with properly formatted data.
    """
    from app.models.enums import BadgeRarity as BadgeRarityEnum
    from app.schemas.badge import BadgeRarity

    # Build badges list from user badges relationship
    badges_list = []
    if user.badges:
        for user_badge in user.badges:
            badge = user_badge.badge
            badge_response = BadgeResponse(
                id=badge.id,
                code=badge.code,
                name_en=badge.name_en,
                name_es=badge.name_es,
                description_en=badge.description_en or "",
                description_es=badge.description_es or "",
                icon_url=badge.icon_url,
                rarity=BadgeRarity(badge.rarity.value) if isinstance(badge.rarity, BadgeRarityEnum) else badge.rarity,
                multa_reward=badge.multa_reward,
                is_nft=badge.is_nft,
            )
            badges_list.append(
                UserBadgeResponse(
                    badge=badge_response,
                    awarded_at=user_badge.awarded_at,
                    nft_mint_address=user_badge.nft_mint_address,
                )
            )

    # Build level response
    level_response = None
    if user.level:
        level_response = LevelResponse(
            id=user.level.id,
            tier=user.level.tier,
            title_en=user.level.title_en,
            title_es=user.level.title_es,
            min_points=user.level.min_points,
            icon_url=user.level.icon_url,
            multa_bonus=user.level.multa_bonus,
        )

    # Map user role from model enum to schema enum
    from app.models.enums import UserRole as UserRoleEnum
    role_value = user.role.value if isinstance(user.role, UserRoleEnum) else user.role
    # Map model role to schema role (citizen -> user)
    role_mapping = {
        "citizen": UserRole.USER,
        "user": UserRole.USER,
        "verifier": UserRole.VERIFIER,
        "moderator": UserRole.MODERATOR,
        "admin": UserRole.ADMIN,
    }
    schema_role = role_mapping.get(role_value, UserRole.USER)

    return UserProfile(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name or user.username or "",
        avatar_url=user.avatar_url,
        points=user.points,
        level=level_response,
        badges=badges_list,
        created_at=user.created_at,
        email=user.email,
        phone_number=user.phone_number,
        wallet_address=user.wallet_address,
        reputation_score=user.reputation_score,
        is_verified=user.is_verified,
        role=schema_role,
    )


def _create_tokens(user_id: str) -> TokenResponse:
    """Create access and refresh tokens for a user.

    Args:
        user_id: The user's UUID as a string.

    Returns:
        TokenResponse with access and refresh tokens.
    """
    # Create access token
    access_token = create_access_token(subject=user_id)

    # Create refresh token (longer expiration)
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


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email, username, and password.",
)
async def register(
    data: RegisterRequest,
    db: DbSession,
) -> TokenResponse:
    """Register a new user account.

    Creates a new user with the provided credentials. The password must meet
    security requirements (min 8 chars, at least 1 letter and 1 number).

    Args:
        data: Registration data including email, username, and password.
        db: Database session.

    Returns:
        TokenResponse with access and refresh tokens.

    Raises:
        HTTPException: 400 if email or username is already taken.
    """
    auth_service = AuthService(db)

    try:
        user = await auth_service.register(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return _create_tokens(str(user.id))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user",
    description="Authenticate with email and password to receive access tokens.",
)
async def login(
    data: LoginRequest,
    db: DbSession,
) -> TokenResponse:
    """Authenticate a user with email and password.

    Validates the user's credentials and returns JWT tokens for authentication.

    Args:
        data: Login credentials (email and password).
        db: Database session.

    Returns:
        TokenResponse with access and refresh tokens.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate(data.email, data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return _create_tokens(str(user.id))


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a refresh token for a new access token.",
)
async def refresh_token(
    data: RefreshRequest,
    db: DbSession,
) -> TokenResponse:
    """Refresh an access token using a refresh token.

    Validates the refresh token and issues new access and refresh tokens.

    Args:
        data: Refresh token request containing the refresh token.
        db: Database session.

    Returns:
        TokenResponse with new access and refresh tokens.

    Raises:
        HTTPException: 401 if refresh token is invalid.
    """
    from app.core.security import decode_access_token
    from uuid import UUID

    # Decode and validate refresh token
    token_data = decode_access_token(data.refresh_token)
    if token_data is None or token_data.sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists and is active
    try:
        user_id = UUID(token_data.sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return _create_tokens(str(user.id))


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout user",
    description="Invalidate the current access token via Redis blacklist.",
)
async def logout(
    current_user: CurrentUser,
    request: Request,
) -> MessageResponse:
    """Logout the current user.

    Adds the current access token to a Redis blacklist so it cannot
    be reused. The blacklist entry expires when the token would have
    expired naturally.

    Args:
        current_user: The authenticated user.
        request: The incoming HTTP request (to extract the token).

    Returns:
        Success message.
    """
    from app.core.redis import blacklist_token

    # Extract the token from the Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        # Blacklist for the remaining token lifetime (default: 30 min)
        await blacklist_token(
            token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    return MessageResponse(
        message="Successfully logged out",
        success=True,
    )


@router.get(
    "/me",
    response_model=UserProfile,
    summary="Get current user profile",
    description="Retrieve the authenticated user's profile with level and badges.",
)
async def get_me(
    current_user: CurrentUser,
) -> UserProfile:
    """Get the current user's profile.

    Returns the full user profile including level, badges, and statistics.

    Args:
        current_user: The authenticated user.

    Returns:
        UserProfile with user details, level, and badges.
    """
    return _build_user_profile(current_user)


@router.post(
    "/link-wallet",
    response_model=UserProfile,
    summary="Link Solana wallet",
    description="Link a Solana wallet address to the authenticated user's account.",
)
async def link_wallet(
    data: WalletLinkRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> UserProfile:
    """Link a Solana wallet to the user's account.

    Associates a Solana wallet address with the authenticated user's account.
    The wallet address must be valid base58 format (32-44 characters).

    Args:
        data: Wallet link request containing the wallet address.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Updated UserProfile with linked wallet.

    Raises:
        HTTPException: 400 if wallet is already linked to another account.
    """
    auth_service = AuthService(db)

    try:
        user = await auth_service.link_wallet(current_user.id, data.wallet_address)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return _build_user_profile(user)
