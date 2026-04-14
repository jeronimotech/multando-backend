"""Public transparency endpoints.

Aggregate, anonymized platform statistics and open-source disclosure of the
confidence scoring + reward rules. Every endpoint in this module is public
(no authentication) and exposes NO personal data (no plates, no reporter
identities, no exact coordinates).

Responses are cached in Redis for 5 minutes to avoid hammering the
database from public traffic.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.core.redis import get_redis
from app.models import (
    Authority,
    AuthorityUser,
    City,
    Infraction,
    Report,
    ReportStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public-transparency"])


# --- Caching helpers ---------------------------------------------------------

_CACHE_TTL_SECONDS = 60 * 5  # 5 minutes
_CACHE_PREFIX = "public_stats:"


async def _cache_get(key: str) -> dict | None:
    """Read a JSON-serialised cached value, returning None on miss or Redis error."""
    try:
        r = await get_redis()
        raw = await r.get(f"{_CACHE_PREFIX}{key}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:  # pragma: no cover - cache must never break the route
        logger.debug("public_stats cache_get failed for %s: %s", key, exc)
        return None


async def _cache_set(key: str, value: dict, ttl: int = _CACHE_TTL_SECONDS) -> None:
    """Best-effort cache write; swallows Redis errors."""
    try:
        r = await get_redis()
        await r.setex(f"{_CACHE_PREFIX}{key}", ttl, json.dumps(value, default=str))
    except Exception as exc:  # pragma: no cover
        logger.debug("public_stats cache_set failed for %s: %s", key, exc)


# --- /public/stats -----------------------------------------------------------


_APPROVED_STATUSES = (ReportStatus.APPROVED, ReportStatus.VERIFIED)
_REJECTED_STATUSES = (ReportStatus.REJECTED,)
_PENDING_STATUSES = (
    ReportStatus.PENDING,
    ReportStatus.COMMUNITY_VERIFIED,
    ReportStatus.AUTHORITY_REVIEW,
    ReportStatus.DISPUTED,
)


def _empty_stats() -> dict[str, Any]:
    """Return a zero-valued response so empty databases never error."""
    return {
        "total_reports": 0,
        "reports_this_month": 0,
        "authority_approval_rate": 0.0,
        "authority_rejection_rate": 0.0,
        "pending_or_review": 0.0,
        "reports_by_category": {"speed": 0, "safety": 0, "parking": 0, "behavior": 0},
        "reports_by_status": {
            "pending": 0,
            "community_verified": 0,
            "authority_review": 0,
            "approved": 0,
            "rejected": 0,
        },
        "top_cities": [],
        "reports_last_12_months": [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _compute_public_stats(db: AsyncSession) -> dict[str, Any]:
    """Compute the `/public/stats` payload from the database.

    Gracefully returns zero-valued aggregates if the database is empty so that
    the endpoint never 500s on a fresh deployment.
    """
    try:
        now = datetime.now(timezone.utc)

        # --- Total reports ----------------------------------------------
        total_reports_q = await db.execute(select(func.count(Report.id)))
        total_reports = int(total_reports_q.scalar() or 0)

        if total_reports == 0:
            return _empty_stats()

        # --- Reports this (calendar) month ------------------------------
        month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        month_q = await db.execute(
            select(func.count(Report.id)).where(Report.created_at >= month_start)
        )
        reports_this_month = int(month_q.scalar() or 0)

        # --- Status rates + status counts -------------------------------
        status_q = await db.execute(
            select(Report.status, func.count(Report.id)).group_by(Report.status)
        )
        status_rows = status_q.all()
        status_counts: dict[str, int] = {
            "pending": 0,
            "community_verified": 0,
            "authority_review": 0,
            "approved": 0,
            "rejected": 0,
        }
        approved_total = 0
        rejected_total = 0
        pending_total = 0
        for st, cnt in status_rows:
            cnt_int = int(cnt or 0)
            key = getattr(st, "value", st)
            if st in _APPROVED_STATUSES:
                approved_total += cnt_int
                # Merge legacy "verified" into "approved" for the breakdown
                status_counts["approved"] += cnt_int
            elif st in _REJECTED_STATUSES:
                rejected_total += cnt_int
                status_counts["rejected"] += cnt_int
            elif st in _PENDING_STATUSES:
                pending_total += cnt_int
                if key in status_counts:
                    status_counts[key] += cnt_int
                else:
                    status_counts["pending"] += cnt_int

        def _rate(n: int) -> float:
            return round(n / total_reports, 4) if total_reports else 0.0

        approval_rate = _rate(approved_total)
        rejection_rate = _rate(rejected_total)
        pending_rate = _rate(pending_total)

        # --- Reports by infraction category -----------------------------
        cat_q = await db.execute(
            select(Infraction.category, func.count(Report.id))
            .join(Report, Report.infraction_id == Infraction.id)
            .group_by(Infraction.category)
        )
        reports_by_category: dict[str, int] = {
            "speed": 0,
            "safety": 0,
            "parking": 0,
            "behavior": 0,
        }
        for cat, cnt in cat_q.all():
            key = getattr(cat, "value", str(cat))
            if key in reports_by_category:
                reports_by_category[key] += int(cnt or 0)
            else:
                reports_by_category[key] = int(cnt or 0)

        # --- Top cities -------------------------------------------------
        # Prefer City via city_id; fall back to the free-text location_city
        # column for older rows that may not have a joined city id.
        top_cities_q = await db.execute(
            select(City.name, func.count(Report.id).label("c"))
            .join(Report, Report.city_id == City.id)
            .group_by(City.name)
            .order_by(desc("c"))
            .limit(10)
        )
        top_cities = [
            {"name": name, "reports": int(c or 0)}
            for (name, c) in top_cities_q.all()
            if name
        ]
        if not top_cities:
            fallback_q = await db.execute(
                select(Report.location_city, func.count(Report.id).label("c"))
                .where(Report.location_city.isnot(None))
                .group_by(Report.location_city)
                .order_by(desc("c"))
                .limit(10)
            )
            top_cities = [
                {"name": name, "reports": int(c or 0)}
                for (name, c) in fallback_q.all()
                if name
            ]

        # --- Reports by month for last 12 full months -------------------
        # Build the list of YYYY-MM keys starting 11 months ago.
        year = now.year
        month = now.month
        months: list[str] = []
        for i in range(11, -1, -1):
            y = year
            m = month - i
            while m <= 0:
                m += 12
                y -= 1
            months.append(f"{y:04d}-{m:02d}")

        cutoff = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(
            days=370
        )
        month_key = func.to_char(Report.created_at, "YYYY-MM")
        monthly_q = await db.execute(
            select(month_key.label("m"), func.count(Report.id).label("c"))
            .where(Report.created_at >= cutoff)
            .group_by("m")
        )
        counts_by_month = {m: int(c or 0) for (m, c) in monthly_q.all()}
        reports_last_12_months = [
            {"month": m, "count": counts_by_month.get(m, 0)} for m in months
        ]

        return {
            "total_reports": total_reports,
            "reports_this_month": reports_this_month,
            "authority_approval_rate": approval_rate,
            "authority_rejection_rate": rejection_rate,
            "pending_or_review": pending_rate,
            "reports_by_category": reports_by_category,
            "reports_by_status": status_counts,
            "top_cities": top_cities,
            "reports_last_12_months": reports_last_12_months,
            "generated_at": now.isoformat(),
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("public_stats aggregation failed: %s", exc)
        return _empty_stats()


@router.get(
    "/stats",
    summary="Public platform statistics",
    description=(
        "Aggregate, anonymized monthly statistics. No personal data is "
        "returned — no plates, no reporter info, no exact coordinates. "
        "Cached for 5 minutes."
    ),
)
async def get_public_stats(db: DbSession) -> dict[str, Any]:
    """Return platform-wide aggregate statistics."""
    cached = await _cache_get("stats_v1")
    if cached is not None:
        return cached
    payload = await _compute_public_stats(db)
    await _cache_set("stats_v1", payload)
    return payload


# --- /public/scoring-rules ---------------------------------------------------


_SCORING_RULES: dict[str, Any] = {
    "baseline": 50,
    "factors": [
        {
            "name": "signed_evidence",
            "points": 30,
            "description": "Cryptographically signed capture (Secure Evidence Capture HMAC verified)",
        },
        {
            "name": "has_photo",
            "points": 10,
            "description": "Photo or image evidence attached to the report",
        },
        {
            "name": "valid_gps",
            "points": 10,
            "description": "Coordinates fall within Colombian bounds",
        },
        {
            "name": "valid_plate",
            "points": 10,
            "description": "Plate matches Colombian format (AAA### / AAA##A)",
        },
        {
            "name": "reporter_reputation",
            "points": "0-15",
            "description": "Scaled by the reporter's historical approval ratio",
        },
        {
            "name": "community_verifications",
            "points": "5 each (max 20)",
            "description": "Each community 'agrees' vote adds +5 up to a cap of +20",
        },
        {
            "name": "community_rejections",
            "points": "-10 each (min -30)",
            "description": "Each community 'disagrees' vote subtracts -10 down to -30",
        },
    ],
    "min": 0,
    "max": 100,
    "notes": (
        "The final score is the sum of the baseline and all applicable factor "
        "contributions, clamped to [0, 100]. The same rules are used by the "
        "open-source ConfidenceScorer service."
    ),
}


@router.get(
    "/scoring-rules",
    summary="Open-source confidence scoring rules",
    description=(
        "Returns the confidence scorer rules in a human-readable JSON form. "
        "These are the exact rules applied by the ConfidenceScorer service."
    ),
)
async def get_scoring_rules() -> dict[str, Any]:
    """Return the scoring rules used by the confidence scorer."""
    return _SCORING_RULES


# --- /public/reward-rules ----------------------------------------------------


def _reward_rules() -> dict[str, Any]:
    """Build the reward-rules payload from the constants in the rewards code."""
    # Imported lazily to avoid a circular import at module load time.
    from app.services.gamification import (
        DAILY_LOGIN_MULTA,
        DAILY_LOGIN_POINTS,
        REFERRAL_MULTA,
        REFERRAL_POINTS,
    )
    from app.services.verification import (
        REJECTION_MULTA,
        REJECTION_POINTS,
        REPORTER_MULTA_ON_VERIFY,
        REPORTER_POINTS_ON_VERIFY,
        VERIFIER_MULTA,
        VERIFIER_POINTS,
    )

    def _fmt(v: Decimal | int) -> float | int:
        if isinstance(v, Decimal):
            return float(v)
        return int(v)

    return {
        "currency": "MULTA",
        "actions": [
            {
                "action": "report_verified",
                "description": "Reporter earns these rewards once their report is verified by the community or approved by an authority.",
                "points": _fmt(REPORTER_POINTS_ON_VERIFY),
                "multa": _fmt(REPORTER_MULTA_ON_VERIFY),
            },
            {
                "action": "verification_done",
                "description": "A community verifier earns a small reward for each valid verification they contribute.",
                "points": _fmt(VERIFIER_POINTS),
                "multa": _fmt(VERIFIER_MULTA),
            },
            {
                "action": "rejection_done",
                "description": "Verifier reward for catching a bad report (rejection participation).",
                "points": _fmt(REJECTION_POINTS),
                "multa": _fmt(REJECTION_MULTA),
            },
            {
                "action": "daily_login",
                "description": "Small engagement reward granted once per 24h on first login.",
                "points": _fmt(DAILY_LOGIN_POINTS),
                "multa": _fmt(DAILY_LOGIN_MULTA),
            },
            {
                "action": "referral",
                "description": "Reward for each successful referral of a new active user.",
                "points": _fmt(REFERRAL_POINTS),
                "multa": _fmt(REFERRAL_MULTA),
            },
        ],
        "notes": (
            "Monthly rewards are capped per user to prevent abuse and bounty-hunting. "
            "False reports deduct points. Badge bonuses are defined separately and "
            "depend on the badge earned."
        ),
    }


@router.get(
    "/reward-rules",
    summary="Open-source reward rules",
    description=(
        "Returns the point and MULTA token reward amounts granted for every "
        "reward-earning action, sourced from the constants in the rewards code."
    ),
)
async def get_reward_rules() -> dict[str, Any]:
    """Return the reward rules as a JSON document."""
    return _reward_rules()


# --- /authorities/{authority_id}/public --------------------------------------
#
# The instructions place this endpoint alongside the public transparency
# router, so it is grouped here. The path is plural / public so it never
# collides with the authenticated /authorities router.


public_authority_router = APIRouter(
    prefix="/authorities", tags=["public-transparency"]
)


async def _authority_public_profile(
    db: AsyncSession, authority_id: int
) -> dict[str, Any] | None:
    """Compute a public profile for a given authority.

    Returns None if the authority does not exist.
    """
    auth_q = await db.execute(
        select(Authority).where(Authority.id == authority_id)
    )
    authority = auth_q.scalar_one_or_none()
    if authority is None:
        return None

    # Find the set of user_ids that belong to this authority so we can
    # attribute validations/rejections to it.
    members_q = await db.execute(
        select(AuthorityUser.user_id).where(
            AuthorityUser.authority_id == authority_id
        )
    )
    member_ids = [uid for (uid,) in members_q.all()]

    validation_count = 0
    rejection_count = 0
    avg_processing_hours: float | None = None

    if member_ids:
        approved_q = await db.execute(
            select(func.count(Report.id)).where(
                and_(
                    Report.authority_validator_id.in_(member_ids),
                    Report.status.in_(_APPROVED_STATUSES),
                )
            )
        )
        validation_count = int(approved_q.scalar() or 0)

        rejected_q = await db.execute(
            select(func.count(Report.id)).where(
                and_(
                    Report.authority_validator_id.in_(member_ids),
                    Report.status.in_(_REJECTED_STATUSES),
                )
            )
        )
        rejection_count = int(rejected_q.scalar() or 0)

        # Average processing time = authority_validated_at - created_at (hours)
        delta = Report.authority_validated_at - Report.created_at
        avg_q = await db.execute(
            select(func.avg(func.extract("epoch", delta))).where(
                and_(
                    Report.authority_validator_id.in_(member_ids),
                    Report.authority_validated_at.isnot(None),
                )
            )
        )
        avg_seconds = avg_q.scalar()
        if avg_seconds is not None:
            try:
                avg_processing_hours = round(float(avg_seconds) / 3600.0, 2)
            except (TypeError, ValueError):
                avg_processing_hours = None

    return {
        "id": authority.id,
        "name": authority.name,
        "code": authority.code,
        "city": authority.city,
        "country": authority.country,
        "validation_count": validation_count,
        "rejection_count": rejection_count,
        "average_processing_time_hours": avg_processing_hours,
        "active_since": (
            authority.created_at.isoformat() if authority.created_at else None
        ),
    }


@public_authority_router.get(
    "/{authority_id}/public",
    summary="Public authority profile",
    description=(
        "Public, anonymous view of an authority's activity. Returns name, "
        "city, counts of validated and rejected reports, average processing "
        "time, and the active-since date. Never exposes staff details, "
        "contact info, or API keys."
    ),
)
async def get_authority_public_profile(
    authority_id: int, db: DbSession
) -> dict[str, Any]:
    """Return a public-safe profile for an authority, or a stub if not found."""
    cache_key = f"authority_public:{authority_id}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return cached
    payload = await _authority_public_profile(db, authority_id)
    if payload is None:
        payload = {
            "id": authority_id,
            "name": None,
            "code": None,
            "city": None,
            "country": None,
            "validation_count": 0,
            "rejection_count": 0,
            "average_processing_time_hours": None,
            "active_since": None,
        }
    await _cache_set(cache_key, payload)
    return payload
