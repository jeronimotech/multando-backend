"""Redis connection and token blacklist management."""

from typing import Optional

import redis.asyncio as redis

from app.core.config import settings

# Global Redis connection pool
_redis_pool: Optional[redis.Redis] = None

TOKEN_BLACKLIST_PREFIX = "token_blacklist:"


async def get_redis() -> redis.Redis:
    """Get or create Redis connection."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
        )
    return _redis_pool


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


async def blacklist_token(token: str, expires_in: int) -> None:
    """Add a token to the blacklist.

    Args:
        token: The JWT token string to blacklist.
        expires_in: Seconds until the blacklist entry expires
                    (should match the token's remaining lifetime).
    """
    r = await get_redis()
    key = f"{TOKEN_BLACKLIST_PREFIX}{token}"
    await r.setex(key, expires_in, "1")


async def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted.

    Args:
        token: The JWT token string to check.

    Returns:
        True if the token is blacklisted.
    """
    try:
        r = await get_redis()
        key = f"{TOKEN_BLACKLIST_PREFIX}{token}"
        result = await r.get(key)
        return result is not None
    except (redis.ConnectionError, redis.TimeoutError):
        # If Redis is unavailable, allow the token (fail open for availability)
        return False
