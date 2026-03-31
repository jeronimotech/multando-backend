"""Authentication service for user registration, login, and wallet linking."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_password_hash, verify_password
from app.models import Level, User, UserBadge
from app.schemas.auth import RegisterRequest


class AuthService:
    """Service for handling authentication operations.

    This service provides methods for user registration, authentication,
    and wallet management.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the auth service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def register(self, data: RegisterRequest) -> User:
        """Register a new user.

        Creates a new user account with the provided data. The password is
        hashed before storage, and the user is assigned the default level (tier 1).

        Args:
            data: Registration data including email, username, and password.

        Returns:
            The newly created User object.

        Raises:
            ValueError: If email or username is already taken.
        """
        # Check if email exists
        existing_email = await self.get_user_by_email(data.email)
        if existing_email:
            raise ValueError("Email is already registered")

        # Check if username exists
        existing_username = await self.get_user_by_username(data.username)
        if existing_username:
            raise ValueError("Username is already taken")

        # Get default level (tier 1)
        default_level = await self._get_default_level()

        # Create user with hashed password
        user = User(
            email=data.email,
            username=data.username,
            password_hash=get_password_hash(data.password),
            display_name=data.display_name or data.username,
            locale=data.locale,
            level_id=default_level.id if default_level else None,
            is_active=True,
            is_verified=False,
        )

        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        # Auto-provision custodial wallet for the new user
        from app.services.wallet import WalletService

        wallet_service = WalletService(self.db)
        await wallet_service.create_custodial_wallet(user.id)

        # Load relationships
        user = await self.get_user_by_id(user.id)
        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate a user with email and password.

        Verifies the user's credentials and updates their last login timestamp.

        Args:
            email: User's email address.
            password: User's plain text password.

        Returns:
            The authenticated User object if credentials are valid, None otherwise.
        """
        user = await self.get_user_by_email(email)
        if not user:
            return None

        if not user.password_hash:
            return None

        if not verify_password(password, user.password_hash):
            return None

        # Update last login timestamp
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()

        return user

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by their email address.

        Args:
            email: The email address to search for.

        Returns:
            The User object if found, None otherwise.
        """
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.level),
                selectinload(User.badges).selectinload(UserBadge.badge),
            )
            .where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> User | None:
        """Get a user by their username.

        Args:
            username: The username to search for.

        Returns:
            The User object if found, None otherwise.
        """
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.level),
                selectinload(User.badges).selectinload(UserBadge.badge),
            )
            .where(User.username == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get a user by their ID.

        Args:
            user_id: The UUID of the user to find.

        Returns:
            The User object if found, None otherwise.
        """
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.level),
                selectinload(User.badges).selectinload(UserBadge.badge),
            )
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_wallet(self, wallet_address: str) -> User | None:
        """Get a user by their wallet address.

        Args:
            wallet_address: The Solana wallet address to search for.

        Returns:
            The User object if found, None otherwise.
        """
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.level),
                selectinload(User.badges).selectinload(UserBadge.badge),
            )
            .where(User.wallet_address == wallet_address)
        )
        return result.scalar_one_or_none()

    async def link_wallet(self, user_id: UUID, wallet_address: str) -> User:
        """Link a Solana wallet to a user account.

        Args:
            user_id: The UUID of the user to update.
            wallet_address: The Solana wallet address to link.

        Returns:
            The updated User object.

        Raises:
            ValueError: If wallet is already linked to another account or user not found.
        """
        # Check if wallet is already linked to another user
        existing_wallet_user = await self.get_user_by_wallet(wallet_address)
        if existing_wallet_user and existing_wallet_user.id != user_id:
            raise ValueError("Wallet address is already linked to another account")

        # Get the user
        user = await self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Update wallet address
        user.wallet_address = wallet_address
        await self.db.flush()

        # Reload user with relationships
        return await self.get_user_by_id(user_id)

    async def _get_default_level(self) -> Level | None:
        """Get the default level (tier 1) for new users.

        Returns:
            The Level object for tier 1, or None if not found.
        """
        result = await self.db.execute(
            select(Level).where(Level.tier == 1)
        )
        return result.scalar_one_or_none()
