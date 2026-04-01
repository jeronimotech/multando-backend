"""Verification endpoints for the Multando API.

This module provides endpoints for verifying and rejecting traffic violation reports.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.api.v1.reports import _build_report_detail, _build_report_summary
from app.schemas.report import ReportDetail, ReportList
from app.services.report import ReportService
from app.services.verification import VerificationService

router = APIRouter(prefix="/verification", tags=["verification"])


class RejectReportRequest(BaseModel):
    """Request body for rejecting a report."""

    reason: str = Field(
        min_length=10,
        max_length=500,
        description="Reason for rejecting the report (10-500 characters)",
    )


@router.post(
    "/{report_id}/verify",
    response_model=ReportDetail,
    summary="Verify a report",
    description="Verify a pending traffic infraction report. Awards points to both verifier and reporter.",
)
async def verify_report(
    report_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ReportDetail:
    """Verify a traffic violation report.

    The verifier cannot be the same user who submitted the report.
    Upon verification:
    - Report status changes to 'verified'
    - Verifier earns 5 points and 3 MULTA
    - Reporter earns 15 points and 10 MULTA
    - Both users may level up or earn badges

    Args:
        report_id: The UUID of the report to verify.
        current_user: The authenticated user performing verification.
        db: Database session.

    Returns:
        The verified ReportDetail.

    Raises:
        HTTPException: 400 if report is not pending or verifier is reporter.
        HTTPException: 404 if report not found.
    """
    verification_service = VerificationService(db)

    try:
        report = await verification_service.verify_report(
            report_id=report_id,
            verifier_id=current_user.id,
        )
    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message,
            )
        elif "own report" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_message,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )

    return _build_report_detail(report)


@router.post(
    "/{report_id}/reject",
    response_model=ReportDetail,
    summary="Reject a report",
    description="Reject a pending traffic infraction report with a reason.",
)
async def reject_report(
    report_id: UUID,
    request: RejectReportRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ReportDetail:
    """Reject a traffic violation report.

    The verifier cannot be the same user who submitted the report.
    Upon rejection:
    - Report status changes to 'rejected'
    - Rejection reason is recorded
    - Verifier earns 2 points and 1 MULTA for participating

    Args:
        report_id: The UUID of the report to reject.
        request: Request body containing rejection reason.
        current_user: The authenticated user performing rejection.
        db: Database session.

    Returns:
        The rejected ReportDetail.

    Raises:
        HTTPException: 400 if report is not pending or reason is missing.
        HTTPException: 403 if verifier is the reporter.
        HTTPException: 404 if report not found.
    """
    verification_service = VerificationService(db)

    try:
        report = await verification_service.reject_report(
            report_id=report_id,
            verifier_id=current_user.id,
            reason=request.reason,
        )
    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message,
            )
        elif "own report" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_message,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )

    return _build_report_detail(report)


@router.get(
    "/queue",
    response_model=ReportList,
    summary="Get verification queue",
    description="Get reports pending verification, excluding user's own reports.",
)
async def get_verification_queue(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> ReportList:
    """Get the verification queue.

    Returns pending reports that the current user can verify
    (excludes their own reports). Reports are ordered oldest first
    to ensure fair verification.

    Args:
        current_user: The authenticated user.
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        A paginated list of pending reports.
    """
    report_service = ReportService(db)

    reports, total = await report_service.get_pending_for_verification(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )

    return ReportList(
        items=[_build_report_summary(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )
