"""Celery tasks for submitting verified Bogota reports to the SDM Google Form.

These tasks are triggered when a Bogota report reaches community_verified or
approved status, or periodically to retry failed submissions.
"""

import asyncio
import logging
from datetime import datetime, timezone

from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.celery import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _submit_sdm_async(report_id: str) -> dict:
    """Async implementation of the SDM Bogota submission."""
    from app.core.database import async_session_factory
    from app.integrations.sdm_bogota import SDMBogotaService
    from app.models.report import Report
    from app.models.sdm_submission import SDMSubmission, SDMSubmissionStatus

    async with async_session_factory() as session:
        # Fetch report with evidences and infraction
        stmt = (
            select(Report)
            .options(
                selectinload(Report.evidences),
                selectinload(Report.infraction),
            )
            .where(Report.id == report_id)
        )
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()

        if report is None:
            logger.error("Report %s not found for SDM submission", report_id)
            return {"success": False, "error": "Report not found"}

        # Check if this is a Bogota report
        service = SDMBogotaService()
        if not service.is_bogota_report(report):
            logger.debug(
                "Report %s is not in Bogota, skipping SDM submission", report_id
            )
            return {"success": False, "skipped": True, "reason": "Not in Bogota"}

        # Check if already submitted
        existing_stmt = select(SDMSubmission).where(
            SDMSubmission.report_id == report.id,
            SDMSubmission.status == SDMSubmissionStatus.SUBMITTED,
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            logger.info("Report %s already submitted to SDM", report_id)
            return {"success": True, "message": "Already submitted"}

        # Get or create the submission record
        sub_stmt = select(SDMSubmission).where(
            SDMSubmission.report_id == report.id
        )
        submission = (await session.execute(sub_stmt)).scalar_one_or_none()
        if submission is None:
            submission = SDMSubmission(
                report_id=report.id,
                status=SDMSubmissionStatus.PENDING,
            )
            session.add(submission)
            await session.flush()

        submission.attempts += 1

        # Submit to SDM
        try:
            result_data = await service.submit_report(report, session)
        except Exception as exc:
            logger.error(
                "SDM submission failed for report %s: %s", report_id, exc
            )
            submission.status = SDMSubmissionStatus.FAILED
            submission.error_message = str(exc)
            await session.commit()
            return {"success": False, "error": str(exc)}

        # Always store the prefill URL
        submission.prefill_url = result_data.get("prefill_url")
        submission.drive_evidence_links = result_data.get("drive_links")

        if result_data.get("success"):
            submission.status = SDMSubmissionStatus.SUBMITTED
            submission.submitted_at = datetime.now(timezone.utc)
            submission.form_response_url = result_data.get("form_response_url")
            submission.error_message = None
            await session.commit()
            logger.info(
                "Report %s submitted to SDM Bogota form", report_id
            )
            return {"success": True, "result": result_data}
        else:
            submission.status = SDMSubmissionStatus.FAILED
            submission.error_message = result_data.get("error", "Unknown failure")
            await session.commit()
            return {"success": False, "error": result_data.get("error")}


@celery_app.task(
    bind=True,
    name="app.integrations.sdm_task.submit_to_sdm",
    max_retries=3,
    acks_late=True,
)
def submit_to_sdm(self: Task, report_id: str) -> dict:
    """Submit a verified Bogota report to the SDM Google Form.

    Called when a Bogota report status changes to community_verified or approved.
    Retries up to 3 times with exponential backoff (30s, 60s, 120s).
    """
    if not settings.SDM_FORM_ENABLED:
        logger.debug("SDM integration disabled, skipping submission")
        return {"success": False, "skipped": True, "reason": "SDM disabled"}

    try:
        result = _run_async(_submit_sdm_async(report_id))
    except Exception as exc:
        backoff = 30 * (2 ** self.request.retries)
        logger.warning(
            "SDM submission for report %s failed (attempt %d/%d), "
            "retrying in %ds: %s",
            report_id,
            self.request.retries + 1,
            self.max_retries + 1,
            backoff,
            exc,
        )
        raise self.retry(exc=exc, countdown=backoff)

    if not result.get("success") and not result.get("skipped"):
        backoff = 30 * (2 ** self.request.retries)
        try:
            raise self.retry(
                exc=Exception(result.get("error", "Unknown error")),
                countdown=backoff,
            )
        except self.MaxRetriesExceededError:
            logger.error(
                "SDM submission for report %s exhausted all retries",
                report_id,
            )
            return result

    return result


@celery_app.task(
    name="app.integrations.sdm_task.process_pending_sdm_submissions",
)
def process_pending_sdm_submissions() -> dict:
    """Process any pending or failed SDM submissions.

    Runs periodically via Celery beat to retry failed submissions
    and pick up any Bogota reports that were missed.
    """
    if not settings.SDM_FORM_ENABLED:
        return {"processed": 0, "reason": "SDM disabled"}

    async def _process():
        from app.core.database import async_session_factory
        from app.models.enums import ReportStatus
        from app.models.report import Report
        from app.models.sdm_submission import SDMSubmission, SDMSubmissionStatus

        async with async_session_factory() as session:
            # Find Bogota reports eligible for SDM submission that don't yet
            # have a submission record.
            subquery = select(SDMSubmission.report_id)
            eligible_statuses = [
                ReportStatus.COMMUNITY_VERIFIED,
                ReportStatus.APPROVED,
                ReportStatus.VERIFIED,
            ]
            # Filter by Bogota bounding box
            missing_stmt = (
                select(Report.id)
                .where(
                    Report.status.in_(eligible_statuses),
                    ~Report.id.in_(subquery),
                    # Broad Bogota bounding box
                    Report.latitude >= 4.45,
                    Report.latitude <= 4.84,
                    Report.longitude >= -74.27,
                    Report.longitude <= -73.98,
                )
                .limit(20)
            )
            missing_result = await session.execute(missing_stmt)
            missing_ids = [str(row[0]) for row in missing_result.all()]

            # Find failed submissions eligible for retry (max 3 attempts)
            failed_stmt = (
                select(SDMSubmission.report_id)
                .where(
                    SDMSubmission.status == SDMSubmissionStatus.FAILED,
                    SDMSubmission.attempts < 3,
                )
                .limit(10)
            )
            failed_result = await session.execute(failed_stmt)
            failed_ids = [str(row[0]) for row in failed_result.all()]

        all_ids = missing_ids + failed_ids
        for rid in all_ids:
            submit_to_sdm.delay(rid)

        return {
            "queued": len(all_ids),
            "new": len(missing_ids),
            "retry": len(failed_ids),
        }

    return _run_async(_process())
