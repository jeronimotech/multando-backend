"""API dependencies for authentication and authorization.

This module provides FastAPI dependencies for securing endpoints with JWT authentication.
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import Authority, AuthorityUser, User
from app.models.enums import AuthorityRole, UserRole
from app.services.auth import AuthService

# HTTP Bearer security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request = None,
) -> User:
    """Get the current authenticated user from JWT token or service account.

    Supports two auth modes:
    1. JWT Bearer token (standard user auth)
    2. Service account (chatbot): API key + X-On-Behalf-Of header with phone number

    Args:
        credentials: HTTP Authorization credentials.
        db: Async database session.
        request: The HTTP request (for service account headers).

    Returns:
        The authenticated User object.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check for SDK API key auth (X-API-Key header)
    api_key_header = request.headers.get("X-API-Key", "") if request else ""
    if api_key_header and api_key_header.startswith("mult_"):
        from app.services.api_key import ApiKeyService

        api_key_service = ApiKeyService(db)
        api_key_record = await api_key_service.validate_key(api_key_header)
        if api_key_record:
            auth_service = AuthService(db)
            user = await auth_service.get_user_by_id(api_key_record.user_id)
            if user:
                return user

    token = credentials.credentials

    # Service account auth: chatbot uses API key + X-On-Behalf-Of header
    chatbot_key = getattr(settings, "CHATBOT_API_KEY", "")
    if chatbot_key and token == chatbot_key and request:
        phone = request.headers.get("X-On-Behalf-Of", "")
        if phone:
            result = await db.execute(
                select(User).where(User.phone_number == phone)
            )
            user = result.scalar_one_or_none()
            if user:
                return user
        raise credentials_exception

    # Check if token is blacklisted (logout)
    from app.core.redis import is_token_blacklisted

    if await is_token_blacklisted(token):
        raise credentials_exception

    # Decode and validate the JWT token
    token_data = decode_access_token(token)
    if token_data is None or token_data.sub is None:
        raise credentials_exception

    # Get user from database
    try:
        user_id = UUID(token_data.sub)
    except ValueError:
        raise credentials_exception

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(user_id)

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the current active user.

    This dependency extends get_current_user by also checking that the user
    account is active.

    Args:
        current_user: The authenticated user from get_current_user.

    Returns:
        The authenticated and active User object.

    Raises:
        HTTPException: 403 if user account is inactive.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return current_user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Optionally get the current user if authenticated.

    This dependency is useful for endpoints that work both with and without
    authentication, providing different behavior based on auth status.

    Args:
        credentials: Optional HTTP Authorization credentials.
        db: Async database session.

    Returns:
        The authenticated User object if valid token provided, None otherwise.
    """
    if credentials is None:
        return None

    token_data = decode_access_token(credentials.credentials)
    if token_data is None or token_data.sub is None:
        return None

    try:
        user_id = UUID(token_data.sub)
    except ValueError:
        return None

    auth_service = AuthService(db)
    return await auth_service.get_user_by_id(user_id)


# Type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_active_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Role-based dependencies
# ---------------------------------------------------------------------------


async def require_admin(current_user: CurrentUser) -> User:
    """Require the current user to be a platform super-admin.

    Raises:
        HTTPException: 403 if the user is not an admin.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_authority_admin(
    current_user: CurrentUser,
    db: DbSession,
) -> tuple[User, Authority]:
    """Return the (user, authority) pair for a user who is an ADMIN within their authority.

    The user must have at least one AuthorityUser record with role=ADMIN.
    If they belong to multiple authorities as admin, the first one is used.

    Raises:
        HTTPException: 403 if the user has no authority-admin membership.
    """
    result = await db.execute(
        select(AuthorityUser)
        .options(selectinload(AuthorityUser.authority))
        .where(
            AuthorityUser.user_id == current_user.id,
            AuthorityUser.role == AuthorityRole.ADMIN,
        )
        .limit(1)
    )
    au = result.scalar_one_or_none()
    if not au:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authority admin access required",
        )
    return current_user, au.authority


# Annotated aliases for the new dependencies
AdminUser = Annotated[User, Depends(require_admin)]
AuthorityAdmin = Annotated[tuple[User, Authority], Depends(get_current_authority_admin)]

# Enterprise feature gate
from app.core.enterprise import require_enterprise  # noqa: E402

EnterpriseRequired = Depends(require_enterprise)
