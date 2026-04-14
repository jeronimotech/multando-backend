"""Reporter-facing rate limiters and anti-harassment cooldowns.

This module centralises the abuse-prevention checks that run before a
new :class:`~app.models.Report` is created:

* :func:`check_report_rate_limit` — caps how many reports a single
  account can file per hour and per day (Redis sliding counter).
* :func:`check_plate_cooldown` — prevents a single user from
  spam-reporting the same plate and caps the global volume of reports
  for one plate within a 24-hour window, unless the reports come from
  locations at least ``PLATE_COORDINATED_RADIUS_KM`` km apart (which we
  treat as a genuine coordinated pattern).

All limit breaches raise ``HTTPException(429)`` with a JSON body that
tells the caller exactly which limit was hit and when to retry.

Redis is used for lightweight counters so we don't hammer Postgres for
trivial throttle checks. The plate cooldown does hit the DB because it
needs location data that the counter-only approach can't carry.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis
from app.models import Report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rate_limit_response(
    *,
    limit_name: str,
    limit: int,
    window_seconds: int,
    retry_after: int,
    message: str,
) -> HTTPException:
    """Build a consistent 429 HTTPException.

    The JSON body is structured so the frontend can render a useful
    message without parsing natural-language text.
    """
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "error": "rate_limit_exceeded",
            "limit": limit_name,
            "max": limit,
            "window_seconds": window_seconds,
            "retry_after_seconds": retry_after,
            "message": message,
        },
        headers={"Retry-After": str(retry_after)},
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in kilometers.

    Standard Haversine; accurate to <1 meter for the distances we care
    about (tens of km).
    """
    r_km = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r_km * math.asin(math.sqrt(a))


async def _incr_with_expiry(key: str, window_seconds: int) -> int:
    """INCR ``key`` and set its TTL on first write.

    Returns the new counter value. We only call EXPIRE when the counter
    is 1 so an active attacker can't keep refreshing the window.
    """
    r = await get_redis()
    pipe = r.pipeline()
    pipe.incr(key, 1)
    pipe.ttl(key)
    new_value, current_ttl = await pipe.execute()
    if current_ttl is None or current_ttl < 0:
        await r.expire(key, window_seconds)
    return int(new_value)


# ---------------------------------------------------------------------------
# Rate limiters
# ---------------------------------------------------------------------------


async def check_report_rate_limit(
    db: AsyncSession,  # noqa: ARG001 — kept in signature for future DB checks
    user_id: UUID,
) -> None:
    """Enforce per-user report submission caps.

    Raises ``HTTPException(429)`` if the user exceeds either the hourly
    or daily cap defined in ``settings``.

    This is a pre-flight check: call it *before* persisting the new
    report. The counter is incremented on every call (even failed
    ones) so repeated retries can't slip past the limit — that's
    intentional.
    """
    hourly_limit = settings.MAX_REPORTS_PER_HOUR
    daily_limit = settings.MAX_REPORTS_PER_DAY

    hour_key = f"rl:reports:hour:{user_id}"
    day_key = f"rl:reports:day:{user_id}"

    try:
        # Check hourly first (stricter).
        hour_count = await _incr_with_expiry(hour_key, 3600)
        if hour_count > hourly_limit:
            r = await get_redis()
            ttl = await r.ttl(hour_key)
            raise _rate_limit_response(
                limit_name="reports_per_hour",
                limit=hourly_limit,
                window_seconds=3600,
                retry_after=max(1, int(ttl or 3600)),
                message=(
                    f"You've reached the limit of {hourly_limit} reports "
                    "per hour. Please wait before submitting another."
                ),
            )

        day_count = await _incr_with_expiry(day_key, 86400)
        if day_count > daily_limit:
            r = await get_redis()
            ttl = await r.ttl(day_key)
            raise _rate_limit_response(
                limit_name="reports_per_day",
                limit=daily_limit,
                window_seconds=86400,
                retry_after=max(1, int(ttl or 86400)),
                message=(
                    f"You've reached the daily limit of {daily_limit} reports. "
                    "Come back tomorrow."
                ),
            )
    except HTTPException:
        raise
    except Exception:
        # Redis outage must not take the product down. Log and fail
        # open: reporters keep working, but abuse opens up. This is the
        # right availability/security tradeoff for civic reporting.
        logger.warning(
            "Rate limiter Redis call failed for user %s; failing open",
            user_id,
            exc_info=True,
        )


async def check_plate_cooldown(
    db: AsyncSession,
    user_id: UUID,
    plate: str | None,
    lat: float,
    lon: float,
) -> None:
    """Enforce plate-level cooldowns to prevent targeted harassment.

    Two rules:

    1. **Per-user:** the same user can't report the same plate more
       than once in ``PLATE_COOLDOWN_HOURS``.
    2. **Global:** a single plate can't accumulate more than
       ``MAX_REPORTS_PER_PLATE_24H`` reports across all users inside
       the cooldown window *unless* the new report's location is at
       least ``PLATE_COORDINATED_RADIUS_KM`` from every existing one
       — that's evidence of a real, moving offender rather than a
       coordinated pile-on.

    Plates are normalized to upper-case for comparison. Reports without
    a plate (rare) are not throttled at the plate level.
    """
    if not plate:
        return

    normalized = plate.upper().strip()
    cooldown_hours = settings.PLATE_COOLDOWN_HOURS
    window_seconds = cooldown_hours * 3600
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cooldown_hours)

    # Rule 1: per-user duplicate check.
    user_dup_stmt = (
        select(Report.id)
        .where(
            Report.vehicle_plate == normalized,
            Report.reporter_id == user_id,
            Report.created_at >= cutoff,
        )
        .limit(1)
    )
    dup = (await db.execute(user_dup_stmt)).scalar_one_or_none()
    if dup is not None:
        raise _rate_limit_response(
            limit_name="same_plate_per_user_24h",
            limit=1,
            window_seconds=window_seconds,
            retry_after=window_seconds,
            message=(
                f"You've already reported plate {normalized} in the last "
                f"{cooldown_hours} hours. Please avoid duplicate reports."
            ),
        )

    # Rule 2: global volume for this plate within the window.
    max_per_plate = settings.MAX_REPORTS_PER_PLATE_24H
    radius_km = settings.PLATE_COORDINATED_RADIUS_KM

    recent_stmt = select(Report.latitude, Report.longitude).where(
        Report.vehicle_plate == normalized,
        Report.created_at >= cutoff,
    )
    recent = (await db.execute(recent_stmt)).all()

    if len(recent) >= max_per_plate:
        # Allow the report only if it's far enough from every existing
        # sighting — a genuine "spotted again elsewhere" signal.
        far_from_all = all(
            _haversine_km(lat, lon, r_lat, r_lon) >= radius_km
            for r_lat, r_lon in recent
        )
        if not far_from_all:
            raise _rate_limit_response(
                limit_name="plate_reports_24h",
                limit=max_per_plate,
                window_seconds=window_seconds,
                retry_after=window_seconds,
                message=(
                    f"Plate {normalized} has reached {max_per_plate} reports "
                    f"in the last {cooldown_hours} hours from this area. "
                    "New reports from noticeably different locations are "
                    "still accepted."
                ),
            )
