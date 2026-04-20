"""Enterprise-only endpoints.

All endpoints in this module require a valid enterprise license key.
Community edition instances will receive 403 on any request.

Provides:
- Advanced analytics (overview, heatmap, trends, reporter stats)
- Multi-tenant authority dashboard
- White-label configuration
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.core.config import settings
from app.core.enterprise import require_enterprise
from app.services.analytics import AnalyticsService

router = APIRouter(
    prefix="/enterprise",
    tags=["enterprise"],
    dependencies=[Depends(require_enterprise)],
)


# ---------------------------------------------------------------------------
# Advanced Analytics
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/overview",
    summary="Platform-wide analytics overview",
    description=(
        "Returns aggregate metrics: total reports with trends, approval rate, "
        "avg response time, top infraction types, top cities, and reporter "
        "activity distribution."
    ),
)
async def analytics_overview(
    db: DbSession,
    current_user: CurrentUser,
    date_from: date | None = Query(default=None, description="Start date (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="End date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Platform-wide analytics overview with optional date range filters."""
    service = AnalyticsService(db)
    return await service.get_overview(date_from=date_from, date_to=date_to)


@router.get(
    "/analytics/heatmap",
    summary="Report heatmap data",
    description=(
        "Returns a grid of lat/lon buckets (rounded to 2 decimal places) with "
        "report counts, suitable for heatmap visualization."
    ),
)
async def analytics_heatmap(
    db: DbSession,
    current_user: CurrentUser,
    city_id: int | None = Query(default=None, description="Filter by city ID"),
    date_from: date | None = Query(default=None, description="Start date"),
    date_to: date | None = Query(default=None, description="End date"),
) -> list[dict[str, Any]]:
    """Heatmap coordinate buckets with report density."""
    service = AnalyticsService(db)
    return await service.get_heatmap(
        city_id=city_id, date_from=date_from, date_to=date_to
    )


@router.get(
    "/analytics/trends",
    summary="Time-series report trends",
    description=(
        "Reports per day/week/month, optionally filtered by infraction type "
        "or city. Returns arrays suitable for charting."
    ),
)
async def analytics_trends(
    db: DbSession,
    current_user: CurrentUser,
    group_by: str = Query(default="day", description="Grouping: day, week, or month"),
    date_from: date | None = Query(default=None, description="Start date"),
    date_to: date | None = Query(default=None, description="End date"),
    infraction_id: int | None = Query(default=None, description="Filter by infraction"),
    city_id: int | None = Query(default=None, description="Filter by city"),
) -> list[dict[str, Any]]:
    """Time-series trends for charting."""
    service = AnalyticsService(db)
    return await service.get_trends(
        group_by=group_by,
        date_from=date_from,
        date_to=date_to,
        infraction_id=infraction_id,
        city_id=city_id,
    )


@router.get(
    "/analytics/reporters",
    summary="Reporter activity statistics",
    description=(
        "Most active reporters (anonymized IDs), rejection rates, and average "
        "reports per user. Useful for authority quality assessment."
    ),
)
async def analytics_reporters(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100, description="Number of top reporters"),
) -> list[dict[str, Any]]:
    """Anonymized reporter activity stats."""
    service = AnalyticsService(db)
    return await service.get_reporter_stats(limit=limit)


# ---------------------------------------------------------------------------
# Multi-tenant Authority Dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/authorities",
    summary="List all authorities with stats",
    description=(
        "Returns all authorities with their validation counts, rejection "
        "counts, and average processing times."
    ),
)
async def list_authorities_with_stats(
    db: DbSession,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """List authorities with performance stats."""
    from sqlalchemy import select
    from app.models import Authority, AuthorityUser, Report, ReportStatus

    # Get all authorities
    auth_q = await db.execute(select(Authority))
    authorities = auth_q.scalars().all()

    results = []
    for authority in authorities:
        # Get member IDs
        members_q = await db.execute(
            select(AuthorityUser.user_id).where(
                AuthorityUser.authority_id == authority.id
            )
        )
        member_ids = [uid for (uid,) in members_q.all()]

        validation_count = 0
        rejection_count = 0
        avg_hours: float | None = None

        if member_ids:
            from sqlalchemy import func

            v_q = await db.execute(
                select(func.count(Report.id)).where(
                    Report.authority_validator_id.in_(member_ids),
                    Report.status.in_(
                        [ReportStatus.APPROVED, ReportStatus.VERIFIED]
                    ),
                )
            )
            validation_count = int(v_q.scalar() or 0)

            r_q = await db.execute(
                select(func.count(Report.id)).where(
                    Report.authority_validator_id.in_(member_ids),
                    Report.status == ReportStatus.REJECTED,
                )
            )
            rejection_count = int(r_q.scalar() or 0)

            delta = Report.authority_validated_at - Report.created_at
            avg_q = await db.execute(
                select(func.avg(func.extract("epoch", delta))).where(
                    Report.authority_validator_id.in_(member_ids),
                    Report.authority_validated_at.isnot(None),
                )
            )
            avg_sec = avg_q.scalar()
            if avg_sec is not None:
                avg_hours = round(float(avg_sec) / 3600.0, 2)

        results.append(
            {
                "id": authority.id,
                "name": authority.name,
                "code": authority.code,
                "city": authority.city,
                "validation_count": validation_count,
                "rejection_count": rejection_count,
                "avg_processing_time_hours": avg_hours,
            }
        )

    return results


@router.get(
    "/authorities/{authority_id}/performance",
    summary="Authority performance metrics",
    description=(
        "Detailed performance for a specific authority: daily throughput, "
        "backlog size, avg time-to-decision, rejection breakdown by reason."
    ),
)
async def authority_performance(
    authority_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Detailed authority performance metrics."""
    service = AnalyticsService(db)
    return await service.get_authority_performance(authority_id)


# ---------------------------------------------------------------------------
# White-label Configuration
# ---------------------------------------------------------------------------


@router.get(
    "/config",
    summary="Get white-label configuration",
    description="Returns current white-label settings for the platform.",
)
async def get_whitelabel_config(current_user: CurrentUser) -> dict[str, Any]:
    """Return current white-label configuration."""
    return {
        "platform_name": settings.PLATFORM_NAME,
        "logo_url": settings.PLATFORM_LOGO_URL,
        "primary_color": settings.PLATFORM_PRIMARY_COLOR,
        "support_email": settings.PLATFORM_SUPPORT_EMAIL,
    }


@router.put(
    "/config",
    summary="Update white-label configuration",
    description=(
        "Update white-label settings. Requires admin role. Note: changes are "
        "applied to the in-memory settings only; persist via environment "
        "variables for production."
    ),
)
async def update_whitelabel_config(
    admin_user: AdminUser,
    platform_name: str | None = Query(default=None),
    logo_url: str | None = Query(default=None),
    primary_color: str | None = Query(default=None),
    support_email: str | None = Query(default=None),
) -> dict[str, Any]:
    """Update white-label configuration (admin only).

    Updates in-memory settings. For persistence, update environment variables.
    """
    if platform_name is not None:
        settings.PLATFORM_NAME = platform_name  # type: ignore[misc]
    if logo_url is not None:
        settings.PLATFORM_LOGO_URL = logo_url  # type: ignore[misc]
    if primary_color is not None:
        settings.PLATFORM_PRIMARY_COLOR = primary_color  # type: ignore[misc]
    if support_email is not None:
        settings.PLATFORM_SUPPORT_EMAIL = support_email  # type: ignore[misc]

    return {
        "message": "White-label configuration updated",
        "config": {
            "platform_name": settings.PLATFORM_NAME,
            "logo_url": settings.PLATFORM_LOGO_URL,
            "primary_color": settings.PLATFORM_PRIMARY_COLOR,
            "support_email": settings.PLATFORM_SUPPORT_EMAIL,
        },
    }
