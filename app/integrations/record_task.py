"""Celery tasks for submitting verified reports to the RECORD form.

These tasks are triggered when a report's status changes to VERIFIED, or
periodically to retry any pending/failed submissions.
"""

import asyncio
import logging
from datetime import datetime

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


async def _submit_report_async(report_id: str) -> dict:
    """Async implementation of the RECORD submission."""
    from app.core.database import async_session_factory
    from app.integrations.department_mapper import (
        CityNotMappedError,
        get_department_and_city,
    )
    from app.integrations.record_submitter import RecordSubmissionError, RecordSubmitter
    from app.models.record_submission import RecordSubmission, RecordSubmissionStatus
    from app.models.report import Evidence, Report

    async with async_session_factory() as session:
        # Fetch report with evidences
        stmt = (
            select(Report)
            .options(selectinload(Report.evidences))
            .where(Report.id == report_id)
        )
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()

        if report is None:
            logger.error("Report %s not found", report_id)
            return {"success": False, "error": "Report not found"}

        # Check if already submitted
        existing_stmt = select(RecordSubmission).where(
            RecordSubmission.report_id == report.id,
            RecordSubmission.status == RecordSubmissionStatus.SUBMITTED,
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            logger.info("Report %s already submitted to RECORD", report_id)
            return {"success": True, "message": "Already submitted"}

        # Get or create the submission record
        sub_stmt = select(RecordSubmission).where(
            RecordSubmission.report_id == report.id
        )
        submission = (await session.execute(sub_stmt)).scalar_one_or_none()
        if submission is None:
            submission = RecordSubmission(
                report_id=report.id,
                status=RecordSubmissionStatus.PENDING,
            )
            session.add(submission)
            await session.flush()

        submission.attempts += 1

        # Map city to department
        city_name = report.location_city or ""
        try:
            department, municipality = get_department_and_city(city_name)
        except CityNotMappedError as exc:
            logger.warning("Skipping RECORD submission: %s", exc)
            submission.status = RecordSubmissionStatus.SKIPPED
            submission.error_message = str(exc)
            await session.commit()
            return {"success": False, "error": str(exc), "skipped": True}

        # Format date and time from incident_datetime
        incident_dt: datetime = report.incident_datetime
        event_date = incident_dt.strftime("%d/%m/%y")
        event_time = incident_dt.strftime("%H:%M")

        # Collect evidence URLs
        evidence_urls = [e.url for e in report.evidences if e.url]

        # Build submission payload
        payload = {
            "department": department,
            "city": municipality,
            "event_date": event_date,
            "event_time": event_time,
            "evidence_urls": evidence_urls,
        }

        # Submit to RECORD (with screenshots)
        submitter = RecordSubmitter(report_id=str(report.id))
        try:
            result = await submitter.submit_report(payload)
        except RecordSubmissionError as exc:
            logger.error(
                "RECORD submission failed for report %s: %s", report_id, exc
            )
            submission.status = RecordSubmissionStatus.FAILED
            submission.error_message = str(exc)
            await session.commit()
            return {"success": False, "error": str(exc)}

        if result.get("success"):
            submission.status = RecordSubmissionStatus.SUBMITTED
            submission.submitted_at = datetime.utcnow()
            response_data = (
                result.get("response_data")
                if isinstance(result.get("response_data"), dict)
                else {"raw": str(result.get("response_data", ""))}
            )
            # Store screenshot URLs as proof of government submission
            response_data["screenshots"] = result.get("screenshots", [])
            submission.response_data = response_data
            submission.error_message = None
            await session.commit()
            logger.info(
                "Report %s submitted to RECORD with %d screenshots",
                report_id,
                len(result.get("screenshots", [])),
            )
            return {"success": True, "result": result}
        else:
            submission.status = RecordSubmissionStatus.FAILED
            submission.error_message = result.get("message", "Unknown failure")
            submission.response_data = (
                result.get("response_data")
                if isinstance(result.get("response_data"), dict)
                else {"raw": str(result.get("response_data", ""))}
            )
            await session.commit()
            return {"success": False, "error": result.get("message")}


@celery_app.task(
    bind=True,
    name="app.integrations.record_task.submit_to_record",
    max_retries=3,
    acks_late=True,
)
def submit_to_record(self: Task, report_id: str) -> dict:
    """Submit a verified report to RECORD.

    Called when a report status changes to VERIFIED.
    Retries up to 3 times with exponential backoff (30s, 60s, 120s).
    """
    if not settings.RECORD_ENABLED:
        logger.debug("RECORD integration disabled, skipping submission")
        return {"success": False, "skipped": True, "reason": "RECORD disabled"}

    try:
        result = _run_async(_submit_report_async(report_id))
    except Exception as exc:
        backoff = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s
        logger.warning(
            "RECORD submission for report %s failed (attempt %d/%d), "
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
                "RECORD submission for report %s exhausted all retries",
                report_id,
            )
            return result

    return result


@celery_app.task(
    name="app.integrations.record_task.process_pending_record_submissions",
)
def process_pending_record_submissions() -> dict:
    """Process any pending or failed RECORD submissions.

    Runs periodically via Celery beat to retry failed submissions
    and pick up any reports that were missed.
    """
    if not settings.RECORD_ENABLED:
        return {"processed": 0, "reason": "RECORD disabled"}

    async def _process():
        from app.core.database import async_session_factory
        from app.models.enums import ReportStatus
        from app.models.record_submission import (
            RecordSubmission,
            RecordSubmissionStatus,
        )
        from app.models.report import Report

        async with async_session_factory() as session:
            # Find verified reports without a submission record
            subquery = select(RecordSubmission.report_id)
            missing_stmt = (
                select(Report.id)
                .where(
                    Report.status == ReportStatus.VERIFIED,
                    ~Report.id.in_(subquery),
                )
                .limit(20)
            )
            missing_result = await session.execute(missing_stmt)
            missing_ids = [str(row[0]) for row in missing_result.all()]

            # Find failed submissions eligible for retry (max 3 attempts)
            failed_stmt = (
                select(RecordSubmission.report_id)
                .where(
                    RecordSubmission.status == RecordSubmissionStatus.FAILED,
                    RecordSubmission.attempts < 3,
                )
                .limit(10)
            )
            failed_result = await session.execute(failed_stmt)
            failed_ids = [str(row[0]) for row in failed_result.all()]

        all_ids = missing_ids + failed_ids
        for rid in all_ids:
            submit_to_record.delay(rid)

        return {"queued": len(all_ids), "new": len(missing_ids), "retry": len(failed_ids)}

    return _run_async(_process())
