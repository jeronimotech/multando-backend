"""SDM (Secretaría Distrital de Movilidad) Bogota submission endpoints.

Provides endpoints to check SDM submission status, manually trigger
submissions, and get pre-filled form URLs for manual fallback.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models.sdm_submission import SDMSubmission
from app.schemas.sdm_submission import (
    SDMPrefillResponse,
    SDMSubmissionResponse,
    build_sdm_submission_response,
)
from app.services.report import ReportService

router = APIRouter(prefix="/reports", tags=["sdm-bogota"])


async def _resolve_report(report_id: str, db):
    """Resolve a report by UUID or short_id."""
    report_service = ReportService(db)
    try:
        uuid_id = UUID(report_id)
        return await report_service.get_by_id(uuid_id)
    except ValueError:
        return await report_service.get_by_short_id(report_id)


@router.get(
    "/{report_id}/sdm-submission",
    response_model=SDMSubmissionResponse,
    summary="Get SDM submission status",
    description=(
        "Returns the current SDM (Bogota) form submission status for a report, "
        "including any pre-fill URLs and Drive evidence links."
    ),
)
async def get_sdm_submission(
    report_id: str,
    db: DbSession,
) -> SDMSubmissionResponse:
    """Return the SDMSubmission linked to the report."""
    report = await _resolve_report(report_id, db)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    result = await db.execute(
        select(SDMSubmission).where(SDMSubmission.report_id == report.id)
    )
    submission = result.scalar_one_or_none()
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No SDM submission exists for this report",
        )

    response = build_sdm_submission_response(submission)
    assert response is not None
    return response


@router.post(
    "/{report_id}/sdm-submit",
    response_model=SDMSubmissionResponse,
    summary="Manually trigger SDM submission (admin)",
    description=(
        "Manually dispatch an SDM form submission for a Bogota report. "
        "Requires admin privileges. The submission runs asynchronously "
        "via Celery; this endpoint creates or resets the submission record "
        "and enqueues the task."
    ),
)
async def trigger_sdm_submission(
    report_id: str,
    current_user: AdminUser,
    db: DbSession,
) -> SDMSubmissionResponse:
    """Manually trigger SDM submission for a report (admin only)."""
    from app.core.config import settings
    from app.models.sdm_submission import SDMSubmissionStatus

    if not settings.SDM_FORM_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SDM integration is disabled",
        )

    report = await _resolve_report(report_id, db)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    # Get or create submission record
    result = await db.execute(
        select(SDMSubmission).where(SDMSubmission.report_id == report.id)
    )
    submission = result.scalar_one_or_none()

    if submission is None:
        submission = SDMSubmission(
            report_id=report.id,
            status=SDMSubmissionStatus.PENDING,
        )
        db.add(submission)
    else:
        # Reset to pending for re-submission
        submission.status = SDMSubmissionStatus.PENDING
        submission.error_message = None

    await db.flush()
    await db.commit()

    # Dispatch Celery task
    try:
        from app.integrations.sdm_task import submit_to_sdm

        submit_to_sdm.delay(str(report.id))
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to dispatch SDM task for report %s",
            report.id,
            exc_info=True,
        )

    response = build_sdm_submission_response(submission)
    assert response is not None
    return response


@router.get(
    "/{report_id}/sdm-prefill",
    response_model=SDMPrefillResponse,
    summary="Get SDM pre-fill URL",
    description=(
        "Generate a pre-filled Google Form URL for the SDM Bogota form. "
        "Useful for manual submission when automated submission fails or "
        "when the user wants to review before submitting."
    ),
)
async def get_sdm_prefill(
    report_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> SDMPrefillResponse:
    """Generate a pre-filled SDM form URL for manual submission."""
    from app.integrations.sdm_bogota import SDMBogotaService

    report = await _resolve_report(report_id, db)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    service = SDMBogotaService()

    if not service.is_bogota_report(report):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This report is not located in Bogota",
        )

    # Check if we already have drive links from a previous attempt
    existing = await db.execute(
        select(SDMSubmission).where(SDMSubmission.report_id == report.id)
    )
    submission = existing.scalar_one_or_none()
    drive_links = (
        submission.drive_evidence_links
        if submission and isinstance(submission.drive_evidence_links, list)
        else []
    )

    prefill_url = service.build_prefill_url(report, drive_links)

    return SDMPrefillResponse(
        prefill_url=prefill_url,
        report_id=report.id,
    )
