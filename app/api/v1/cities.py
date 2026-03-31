"""City API endpoints.

Public endpoints for listing cities and viewing city-level statistics.
No authentication required.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.city import City
from app.models.report import Report
from app.models.enums import ReportStatus
from app.schemas.city import CityListResponse, CityResponse, CityStatsResponse

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get(
    "",
    response_model=CityListResponse,
    summary="List active cities",
    description="List all active cities where reporting is enabled. Public endpoint, no auth required.",
)
async def list_cities(
    db: AsyncSession = Depends(get_db),
) -> CityListResponse:
    """List all active cities.

    Args:
        db: Async database session.

    Returns:
        List of active cities.
    """
    result = await db.execute(
        select(City).where(City.is_active.is_(True)).order_by(City.name)
    )
    cities = result.scalars().all()
    return CityListResponse(
        items=[CityResponse.model_validate(c) for c in cities]
    )


@router.get(
    "/{city_id}",
    response_model=CityResponse,
    summary="Get city detail",
    description="Get detailed information about a specific city.",
)
async def get_city(
    city_id: int,
    db: AsyncSession = Depends(get_db),
) -> CityResponse:
    """Get a city by ID.

    Args:
        city_id: The city ID.
        db: Async database session.

    Returns:
        City details.

    Raises:
        HTTPException: 404 if city not found.
    """
    city = await db.get(City, city_id)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found",
        )
    return CityResponse.model_validate(city)


@router.get(
    "/{city_id}/stats",
    response_model=CityStatsResponse,
    summary="Get public city statistics",
    description="Get public statistics for a city: total reports, verified count, active reporters.",
)
async def get_city_stats(
    city_id: int,
    db: AsyncSession = Depends(get_db),
) -> CityStatsResponse:
    """Get public statistics for a city.

    Args:
        city_id: The city ID.
        db: Async database session.

    Returns:
        City statistics.

    Raises:
        HTTPException: 404 if city not found.
    """
    city = await db.get(City, city_id)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found",
        )

    # Total reports
    total_result = await db.execute(
        select(func.count()).select_from(Report).where(Report.city_id == city_id)
    )
    total_reports = total_result.scalar() or 0

    # Verified reports
    verified_result = await db.execute(
        select(func.count())
        .select_from(Report)
        .where(Report.city_id == city_id, Report.status == ReportStatus.VERIFIED)
    )
    verified_reports = verified_result.scalar() or 0

    # Active reporters (distinct users who filed reports in this city)
    reporters_result = await db.execute(
        select(func.count(func.distinct(Report.reporter_id)))
        .select_from(Report)
        .where(Report.city_id == city_id)
    )
    active_reporters = reporters_result.scalar() or 0

    return CityStatsResponse(
        city=CityResponse.model_validate(city),
        total_reports=total_reports,
        verified_reports=verified_reports,
        active_reporters=active_reporters,
    )
