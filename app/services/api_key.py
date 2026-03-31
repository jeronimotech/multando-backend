"""Service for managing third-party API keys.

Handles key generation, validation, listing, revocation, and deletion.
Keys are stored as SHA-256 hashes; the raw key is only returned once at creation.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


class ApiKeyService:
    """Service for API key CRUD and validation operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_key(
        self,
        user_id: UUID,
        name: str,
        scopes: list[str] | None = None,
        rate_limit: int = 60,
        expires_in_days: int | None = None,
    ) -> tuple[ApiKey, str]:
        """Generate a new API key for a user.

        Args:
            user_id: Owner of the key.
            name: Developer-given name.
            scopes: Permission scopes.
            rate_limit: Requests per minute.
            expires_in_days: Days until expiry (None = no expiry).

        Returns:
            Tuple of (ApiKey record, raw key string shown only once).
        """
        # Generate the raw key: "mult_" + 40 random hex characters
        raw_key = "mult_" + secrets.token_hex(20)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:8]

        expires_at = None
        if expires_in_days is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        api_key = ApiKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            user_id=user_id,
            is_active=True,
            rate_limit=rate_limit,
            scopes=scopes or [
                "reports:create",
                "reports:read",
                "infractions:read",
                "users:read",
                "balance:read",
            ],
            expires_at=expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)

        return api_key, raw_key

    async def validate_key(self, raw_key: str) -> ApiKey | None:
        """Validate a raw API key and return the record if valid.

        Checks that the key exists, is active, and has not expired.
        Updates last_used_at on success.

        Args:
            raw_key: The full API key string.

        Returns:
            The ApiKey record if valid, None otherwise.
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        result = await self.db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return None

        if not api_key.is_active:
            return None

        if api_key.expires_at is not None:
            now = datetime.now(timezone.utc)
            if now > api_key.expires_at:
                return None

        # Update last used timestamp
        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()

        return api_key

    async def list_keys(self, user_id: UUID) -> tuple[list[ApiKey], int]:
        """List all API keys for a user.

        Args:
            user_id: The user's UUID.

        Returns:
            Tuple of (list of ApiKey records, total count).
        """
        count_result = await self.db.execute(
            select(func.count())
            .select_from(ApiKey)
            .where(ApiKey.user_id == user_id)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id)
            .order_by(ApiKey.created_at.desc())
        )
        items = list(result.scalars().all())

        return items, total

    async def revoke_key(self, user_id: UUID, key_id: int) -> ApiKey | None:
        """Revoke an API key by setting is_active to False.

        Args:
            user_id: Owner's UUID (ensures ownership).
            key_id: The API key's ID.

        Returns:
            The revoked ApiKey record, or None if not found.
        """
        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.user_id == user_id,
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return None

        api_key.is_active = False
        await self.db.flush()
        await self.db.refresh(api_key)
        return api_key

    async def delete_key(self, user_id: UUID, key_id: int) -> bool:
        """Hard-delete an API key.

        Args:
            user_id: Owner's UUID (ensures ownership).
            key_id: The API key's ID.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.db.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.user_id == user_id,
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return False

        await self.db.delete(api_key)
        await self.db.flush()
        return True
