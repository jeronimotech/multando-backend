"""Authority review endpoints.

Authorities use this router to validate reports that will become official
comparendos. The queue is sorted by ``confidence_score`` descending so the
highest-signal reports bubble to the top.

Role gating mirrors the leaderboard endpoints:
    - user.role in (AUTHORITY, ADMIN), OR
    - user has any AuthorityUser membership.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.api.v1.reports import _build_report_detail, _load_record_submission
from app.models import AuthorityUser, Report, ReportStatus, User
from app.models.enums import UserRole
from app.schemas.authority_review import (
    AuthorityApproveRequest,
    AuthorityRejectRequest,
)
from app.schemas.report import ReportDetail, ReportList, ReportStatus as SchemaReportStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/authority/review", tags=["authority-review"])


# ---------------------------------------------------------------------------
# Role gating
# ---------------------------------------------------------------------------


async def _require_authority_role(user: User, db: AsyncSession) -> User:
    """Allow authority/admin users or any AuthorityUser membership."""
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/queue",
    response_model=ReportList,
    summary="Get the authority review queue",
    description=(
        "Return reports awaiting authority validation, sorted by confidence "
        "score descending. Default filter includes both community_verified "
        "and authority_review statuses."
    ),
)
async def get_review_queue(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: Optional[SchemaReportStatus] = Query(
        default=None,
        alias="status",
        description="Restrict to a single status.",
    ),
    city_id: Optional[int] = Query(
        default=None, description="Filter by city ID."
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReportList:
    """Authority queue, ordered by confidence_score DESC, created_at ASC."""
    await _require_authority_role(current_user, db)

    # Default: both statuses that feed the comparendo flow.
    if status_filter is None:
        statuses: list[ReportStatus] = [
            ReportStatus.COMMUNITY_VERIFIED,
            ReportStatus.AUTHORITY_REVIEW,
        ]
    else:
        statuses = [ReportStatus(status_filter.value)]

    base_where = [Report.status.in_(statuses)]
    if city_id is not None:
        base_where.append(Report.city_id == city_id)

    # Count
    count_stmt = select(func.count()).select_from(Report).where(*base_where)
    total = (await db.execute(count_stmt)).scalar_one()

    # Items
    stmt = (
        select(Report)
        .options(
            selectinload(Report.reporter),
            selectinload(Report.verifier),
            selectinload(Report.infraction),
            selectinload(Report.vehicle_type),
            selectinload(Report.evidences),
            selectinload(Report.authority_validator),
        )
        .where(*base_where)
        .order_by(
            Report.confidence_score.desc(),
            Report.created_at.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    reports = list(result.scalars().all())

    # We build full detail responses (caller wants confidence fields), but
    # ReportList expects ReportSummary items. ReportDetail extends
    # ReportSummary so the coercion is safe.
    from app.api.v1.reports import _build_report_summary

    items = [_build_report_summary(r) for r in reports]

    logger.info(
        "authority_review.queue user=%s count=%d total=%d statuses=%s city=%s",
        current_user.id,
        len(items),
        total,
        [s.value for s in statuses],
        city_id,
    )

    return ReportList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


async def _load_report_for_authority(
    db: AsyncSession, report_id: UUID
) -> Report:
    result = await db.execute(
        select(Report)
        .options(
            selectinload(Report.reporter),
            selectinload(Report.verifier),
            selectinload(Report.infraction),
            selectinload(Report.vehicle_type),
            selectinload(Report.evidences),
            selectinload(Report.authority_validator),
        )
        .where(Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    return report


@router.post(
    "/{report_id}/approve",
    response_model=ReportDetail,
    summary="Approve a report as a valid comparendo",
)
async def approve_report(
    report_id: UUID,
    body: AuthorityApproveRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ReportDetail:
    """Authority validates the report into an official comparendo."""
    await _require_authority_role(current_user, db)

    report = await _load_report_for_authority(db, report_id)

    if report.status not in (
        ReportStatus.COMMUNITY_VERIFIED,
        ReportStatus.AUTHORITY_REVIEW,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only reports in community_verified or authority_review "
                "status can be approved."
            ),
        )

    report.status = ReportStatus.APPROVED
    report.authority_validator_id = current_user.id
    report.authority_validated_at = datetime.now(timezone.utc)
    report.authority_notes = body.notes

    await db.flush()

    logger.info(
        "authority_review.approve report=%s authority_user=%s notes_len=%d",
        report.id,
        current_user.id,
        len(body.notes or ""),
    )

    submission = await _load_record_submission(db, report.id)
    # RECORD must NOT re-trigger on authority approval; the unique
    # constraint on record_submission.report_id protects us anyway.
    return _build_report_detail(
        report,
        record_submission=submission,
        include_reporter_identity=True,
        include_rejection_warning=True,
    )


@router.post(
    "/{report_id}/reject",
    response_model=ReportDetail,
    summary="Reject a report from the authority queue",
)
async def authority_reject(
    report_id: UUID,
    body: AuthorityRejectRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ReportDetail:
    """Authority marks the report as rejected, final state."""
    await _require_authority_role(current_user, db)

    report = await _load_report_for_authority(db, report_id)

    if report.status not in (
        ReportStatus.COMMUNITY_VERIFIED,
        ReportStatus.AUTHORITY_REVIEW,
        ReportStatus.PENDING,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only reports in pending, community_verified, or "
                "authority_review status can be rejected by an authority."
            ),
        )

    report.status = ReportStatus.REJECTED
    report.authority_validator_id = current_user.id
    report.authority_validated_at = datetime.now(timezone.utc)
    report.authority_notes = body.reason
    report.rejection_reason = body.reason

    await db.flush()

    # Apply the false-report penalty: points debit + activity log +
    # rejected_reports_count bump. Keep this inside the transaction so
    # the reject status and the penalty are atomic.
    from app.services.verification import VerificationService

    verification_service = VerificationService(db)
    await verification_service.apply_authority_rejection_penalty(report)

    logger.warning(
        "authority_review.reject report=%s authority_user=%s reason_len=%d",
        report.id,
        current_user.id,
        len(body.reason or ""),
    )

    submission = await _load_record_submission(db, report.id)
    return _build_report_detail(
        report,
        record_submission=submission,
        include_reporter_identity=True,
        include_rejection_warning=True,
    )
