"""Bad Drivers Leaderboard endpoints.

Public endpoint returns a ranking of the worst offenders based on verified
reports with plates masked (first 3 chars visible, the rest replaced with
bullets). An authority-only variant exposes unmasked plates and the most
recent report location.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.models import (
    AuthorityUser,
    City,
    Infraction,
    Report,
    ReportStatus,
    User,
    UserRole,
)

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


PeriodLiteral = Literal["all", "month", "week"]


def _period_cutoff(period: PeriodLiteral) -> datetime | None:
    """Return the start datetime for a given period, or None for "all"."""
    if period == "all":
        return None
    now = datetime.now(timezone.utc)
    if period == "month":
        return now - timedelta(days=30)
    if period == "week":
        return now - timedelta(days=7)
    return None


def _mask_plate(plate: str | None) -> str:
    """Mask a plate: first 3 chars visible, rest replaced with bullets (min 3).

    Matches the frontend plate masking logic.
    """
    if not plate:
        return "•••"
    plate = plate.strip()
    if len(plate) <= 3:
        return plate + "•••"
    visible = plate[:3]
    hidden_count = max(3, len(plate) - 3)
    return visible + ("•" * hidden_count)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PlateLocation(BaseModel):
    """Location for a reported plate (authority view only)."""

    lat: float
    lon: float
    address: str | None = None
    city: str | None = None


class PublicLeaderboardEntry(BaseModel):
    """Public-facing leaderboard row.

    Plate numbers are public (already in government records) but we do NOT
    expose exact GPS coordinates or addresses to prevent correlating a
    specific plate with a specific location.
    """

    plate: str = Field(description="Full vehicle plate")
    verified_reports: int = Field(description="Number of verified reports for this plate")
    last_reported_at: datetime | None = Field(
        default=None, description="Most recent report timestamp"
    )
    top_infraction: str | None = Field(
        default=None, description="Most common infraction name for this plate"
    )
    cities: list[str] = Field(
        default_factory=list,
        description="Cities where this plate has been reported (verified only)",
    )


class AuthorityLeaderboardEntry(BaseModel):
    """Authority-only leaderboard row with full plate + location."""

    plate: str = Field(description="Full vehicle plate (authority-only)")
    verified_reports: int
    last_reported_at: datetime | None = None
    top_infraction: str | None = None
    cities: list[str] = Field(default_factory=list)
    last_location: PlateLocation | None = Field(
        default=None, description="Location of the most recent verified report"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _require_authority_user(user: User, db: AsyncSession) -> User:
    """Ensure the current user is authorized to view authority leaderboard data.

    Allowed if:
      - user.role in (AUTHORITY, ADMIN), OR
      - user has any AuthorityUser membership.
    """
    if user.role in (UserRole.AUTHORITY, UserRole.ADMIN):
        return user

    result = await db.execute(
        select(AuthorityUser).where(AuthorityUser.user_id == user.id).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        return user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Authority access required",
    )


async def _aggregate_plate_stats(
    db: AsyncSession,
    *,
    city_id: int | None,
    period: PeriodLiteral,
    limit: int,
) -> list[dict]:
    """Aggregate verified-report counts per plate.

    Returns a list of dicts with: plate, verified_reports, last_reported_at.
    Sorted by verified_reports desc.
    """
    conditions = [
        Report.status == ReportStatus.VERIFIED,
        Report.vehicle_plate.isnot(None),
        Report.vehicle_plate != "",
    ]
    if city_id is not None:
        conditions.append(Report.city_id == city_id)

    cutoff = _period_cutoff(period)
    if cutoff is not None:
        conditions.append(Report.created_at >= cutoff)

    stmt = (
        select(
            Report.vehicle_plate.label("plate"),
            func.count(Report.id).label("verified_reports"),
            func.max(Report.created_at).label("last_reported_at"),
        )
        .where(and_(*conditions))
        .group_by(Report.vehicle_plate)
        .order_by(desc("verified_reports"), desc("last_reported_at"))
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "plate": row.plate,
            "verified_reports": int(row.verified_reports),
            "last_reported_at": row.last_reported_at,
        }
        for row in rows
    ]


async def _top_infraction_for_plate(
    db: AsyncSession,
    plate: str,
    *,
    city_id: int | None,
    cutoff: datetime | None,
) -> str | None:
    """Return the most frequent infraction name for a plate (verified only)."""
    conditions = [
        Report.status == ReportStatus.VERIFIED,
        Report.vehicle_plate == plate,
    ]
    if city_id is not None:
        conditions.append(Report.city_id == city_id)
    if cutoff is not None:
        conditions.append(Report.created_at >= cutoff)

    stmt = (
        select(
            Infraction.name_en.label("name"),
            func.count(Report.id).label("c"),
        )
        .join(Infraction, Report.infraction_id == Infraction.id)
        .where(and_(*conditions))
        .group_by(Infraction.name_en)
        .order_by(desc("c"))
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    return row.name if row else None


async def _cities_for_plate(
    db: AsyncSession,
    plate: str,
    *,
    city_id: int | None,
    cutoff: datetime | None,
) -> list[str]:
    """Return the distinct city names where this plate has verified reports."""
    conditions = [
        Report.status == ReportStatus.VERIFIED,
        Report.vehicle_plate == plate,
    ]
    if city_id is not None:
        conditions.append(Report.city_id == city_id)
    if cutoff is not None:
        conditions.append(Report.created_at >= cutoff)

    stmt = (
        select(func.distinct(City.name))
        .select_from(Report)
        .join(City, Report.city_id == City.id)
        .where(and_(*conditions))
    )
    result = await db.execute(stmt)
    return [name for (name,) in result.all() if name]


async def _last_location_for_plate(
    db: AsyncSession,
    plate: str,
    *,
    city_id: int | None,
    cutoff: datetime | None,
) -> PlateLocation | None:
    """Return the most recent verified report location for a plate."""
    conditions = [
        Report.status == ReportStatus.VERIFIED,
        Report.vehicle_plate == plate,
    ]
    if city_id is not None:
        conditions.append(Report.city_id == city_id)
    if cutoff is not None:
        conditions.append(Report.created_at >= cutoff)

    stmt = (
        select(
            Report.latitude,
            Report.longitude,
            Report.location_address,
            Report.location_city,
        )
        .where(and_(*conditions))
        .order_by(desc(Report.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return PlateLocation(
        lat=row.latitude,
        lon=row.longitude,
        address=row.location_address,
        city=row.location_city,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/plates",
    response_model=list[PublicLeaderboardEntry],
    summary="Public bad-drivers leaderboard",
    description=(
        "Returns the worst offenders sorted by count of VERIFIED reports. "
        "Plate numbers are masked (first 3 characters visible, rest hidden)."
    ),
)
async def get_public_leaderboard(
    db: DbSession,
    city_id: int | None = Query(default=None, description="Filter by city id"),
    period: PeriodLiteral = Query(default="all", description="Time window"),
    limit: int = Query(default=20, ge=1, le=100, description="Max rows to return"),
) -> list[PublicLeaderboardEntry]:
    """Public leaderboard — NO location, plates masked."""
    stats = await _aggregate_plate_stats(
        db, city_id=city_id, period=period, limit=limit
    )
    cutoff = _period_cutoff(period)

    entries: list[PublicLeaderboardEntry] = []
    for row in stats:
        plate = row["plate"]
        top_infraction = await _top_infraction_for_plate(
            db, plate, city_id=city_id, cutoff=cutoff
        )
        cities = await _cities_for_plate(db, plate, city_id=city_id, cutoff=cutoff)
        entries.append(
            PublicLeaderboardEntry(
                plate=plate,
                verified_reports=row["verified_reports"],
                last_reported_at=row["last_reported_at"],
                top_infraction=top_infraction,
                cities=cities,
            )
        )
    return entries


@router.get(
    "/plates/authority",
    response_model=list[AuthorityLeaderboardEntry],
    summary="Authority bad-drivers leaderboard",
    description=(
        "Authority-only leaderboard. Returns the full plate number plus the "
        "most recent verified-report location. Requires authority or admin role, "
        "or membership in an AuthorityUser record."
    ),
)
async def get_authority_leaderboard(
    current_user: CurrentUser,
    db: DbSession,
    city_id: int | None = Query(default=None, description="Filter by city id"),
    period: PeriodLiteral = Query(default="all", description="Time window"),
    limit: int = Query(default=20, ge=1, le=100, description="Max rows to return"),
) -> list[AuthorityLeaderboardEntry]:
    """Authority variant — full plate + last location."""
    await _require_authority_user(current_user, db)

    stats = await _aggregate_plate_stats(
        db, city_id=city_id, period=period, limit=limit
    )
    cutoff = _period_cutoff(period)

    entries: list[AuthorityLeaderboardEntry] = []
    for row in stats:
        plate = row["plate"]
        top_infraction = await _top_infraction_for_plate(
            db, plate, city_id=city_id, cutoff=cutoff
        )
        cities = await _cities_for_plate(db, plate, city_id=city_id, cutoff=cutoff)
        last_location = await _last_location_for_plate(
            db, plate, city_id=city_id, cutoff=cutoff
        )
        entries.append(
            AuthorityLeaderboardEntry(
                plate=plate,
                verified_reports=row["verified_reports"],
                last_reported_at=row["last_reported_at"],
                top_infraction=top_infraction,
                cities=cities,
                last_location=last_location,
            )
        )
    return entries
