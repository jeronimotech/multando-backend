"""Authority (B2B) API endpoints.

This module contains endpoints for authority (government/regulatory body) operations.
Authorities can register, authenticate via API key, and access reports in their jurisdiction.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models import Authority
from app.models.enums import ReportStatus
from app.schemas.authority import (
    AnalyticsResponse,
    AuthorityCreate,
    AuthorityCreatedResponse,
    AuthorityReportFilters,
    AuthorityResponse,
    HeatmapResponse,
)
from app.schemas.report import ReportList, ReportSummary
from app.services.authority import AuthorityService

router = APIRouter(prefix="/authorities", tags=["authorities"])


async def get_authority_from_api_key(
    x_api_key: str = Header(..., description="API key for authentication"),
    db: AsyncSession = Depends(get_db),
) -> Authority:
    """Validate API key and return authority.

    Args:
        x_api_key: API key from request header.
        db: Async database session.

    Returns:
        The authenticated Authority.

    Raises:
        HTTPException: 401 if API key is invalid.
    """
    service = AuthorityService(db)
    authority = await service.validate_api_key(x_api_key)
    if not authority:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return authority


@router.post(
    "/register",
    response_model=AuthorityCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new authority",
    description="Register a new authority. Returns API key (save it, shown only once).",
)
async def register_authority(
    data: AuthorityCreate,
    db: AsyncSession = Depends(get_db),
) -> AuthorityCreatedResponse:
    """Register a new authority.

    Args:
        data: Authority creation data.
        db: Async database session.

    Returns:
        Created authority with API key (shown only once).

    Raises:
        HTTPException: 400 if authority code already exists.
    """
    service = AuthorityService(db)

    # Check if code already exists
    existing = await service.get_by_code(data.code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authority code already registered",
        )

    authority, api_key = await service.create_authority(**data.model_dump())

    return AuthorityCreatedResponse(
        authority=AuthorityResponse.model_validate(authority),
        api_key=api_key,
    )


@router.get(
    "/me",
    response_model=AuthorityResponse,
    summary="Get current authority information",
    description="Get information about the authenticated authority.",
)
async def get_authority_info(
    authority: Authority = Depends(get_authority_from_api_key),
) -> AuthorityResponse:
    """Get current authority information.

    Args:
        authority: The authenticated authority.

    Returns:
        Authority information.
    """
    return AuthorityResponse.model_validate(authority)


@router.get(
    "/reports",
    response_model=ReportList,
    summary="Get reports in jurisdiction",
    description="Get reports in the authority's jurisdiction with optional filters.",
)
async def get_reports(
    filters: AuthorityReportFilters = Depends(),
    authority: Authority = Depends(get_authority_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> ReportList:
    """Get reports in authority's jurisdiction.

    Args:
        filters: Report filter parameters.
        authority: The authenticated authority.
        db: Async database session.

    Returns:
        Paginated list of reports.
    """
    service = AuthorityService(db)

    # Convert status string to enum if provided
    status_enum = None
    if filters.status:
        try:
            status_enum = ReportStatus(filters.status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {filters.status}",
            )

    reports, total = await service.get_reports(
        authority=authority,
        page=filters.page,
        page_size=filters.page_size,
        status=status_enum,
        from_date=filters.from_date,
        to_date=filters.to_date,
    )

    return ReportList(
        items=[ReportSummary.model_validate(r) for r in reports],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
    )


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Get analytics for jurisdiction",
    description="Get analytics data for the authority's jurisdiction.",
)
async def get_analytics(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    authority: Authority = Depends(get_authority_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsResponse:
    """Get analytics for authority's jurisdiction.

    Args:
        from_date: Optional start date filter.
        to_date: Optional end date filter.
        authority: The authenticated authority.
        db: Async database session.

    Returns:
        Analytics data.
    """
    service = AuthorityService(db)
    analytics = await service.get_analytics(
        authority=authority,
        from_date=from_date,
        to_date=to_date,
    )
    return AnalyticsResponse(**analytics)


@router.get(
    "/heatmap",
    response_model=HeatmapResponse,
    summary="Get heatmap data",
    description="Get coordinate data for heatmap visualization.",
)
async def get_heatmap(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    authority: Authority = Depends(get_authority_from_api_key),
    db: AsyncSession = Depends(get_db),
) -> HeatmapResponse:
    """Get heatmap data for visualization.

    Args:
        from_date: Optional start date filter.
        to_date: Optional end date filter.
        authority: The authenticated authority.
        db: Async database session.

    Returns:
        Heatmap coordinate data.
    """
    service = AuthorityService(db)
    points = await service.get_heatmap_data(
        authority=authority,
        from_date=from_date,
        to_date=to_date,
    )
    return HeatmapResponse(points=points)
