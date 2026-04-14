"""Schemas for RECORD (Ministerio de Transporte) submissions."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class RecordSubmissionStatus(str, Enum):
    """Status of a RECORD form submission."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class RecordSubmissionResponse(BaseSchema):
    """Schema exposing RECORD submission state for a report."""

    id: int = Field(description="RecordSubmission identifier")
    report_id: UUID = Field(description="Report this submission belongs to")
    status: RecordSubmissionStatus = Field(
        description="Current status of the RECORD submission"
    )
    submitted_at: datetime | None = Field(
        default=None,
        description="Timestamp when the submission was accepted by RECORD",
    )
    attempts: int = Field(
        default=0, description="Number of submission attempts performed so far"
    )
    error_message: str | None = Field(
        default=None, description="Last error message if submission failed"
    )
    screenshots: list[str] = Field(
        default_factory=list,
        description="URLs of screenshots captured during the government submission",
    )


def build_record_submission_response(
    submission,
) -> RecordSubmissionResponse | None:
    """Build a RecordSubmissionResponse from a RecordSubmission model instance."""
    if submission is None:
        return None

    response_data = submission.response_data or {}
    screenshots_raw = response_data.get("screenshots") or []
    # Only keep string URLs.
    screenshots = [s for s in screenshots_raw if isinstance(s, str)]

    status_value = (
        submission.status.value
        if hasattr(submission.status, "value")
        else str(submission.status)
    )

    return RecordSubmissionResponse(
        id=submission.id,
        report_id=submission.report_id,
        status=RecordSubmissionStatus(status_value),
        submitted_at=submission.submitted_at,
        attempts=submission.attempts or 0,
        error_message=submission.error_message,
        screenshots=screenshots,
    )
