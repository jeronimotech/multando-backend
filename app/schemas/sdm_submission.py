"""Schemas for SDM (Secretaría Distrital de Movilidad) Bogota submissions."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema


class SDMSubmissionStatus(str, Enum):
    """Status of an SDM form submission."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class SDMSubmissionResponse(BaseSchema):
    """Schema exposing SDM submission state for a report."""

    id: int = Field(description="SDMSubmission identifier")
    report_id: UUID = Field(description="Report this submission belongs to")
    status: SDMSubmissionStatus = Field(
        description="Current status of the SDM submission"
    )
    submitted_at: datetime | None = Field(
        default=None,
        description="Timestamp when the form was submitted to SDM",
    )
    attempts: int = Field(
        default=0, description="Number of submission attempts"
    )
    error_message: str | None = Field(
        default=None, description="Last error message if submission failed"
    )
    form_response_url: str | None = Field(
        default=None, description="Confirmation URL from Google Forms"
    )
    prefill_url: str | None = Field(
        default=None,
        description="Pre-filled form URL for manual submission fallback",
    )
    drive_evidence_links: list[str] = Field(
        default_factory=list,
        description="Google Drive shareable links for uploaded evidence",
    )


class SDMPrefillResponse(BaseSchema):
    """Response containing just the pre-fill URL."""

    prefill_url: str = Field(description="Pre-filled Google Form URL")
    report_id: UUID = Field(description="Report this URL is for")


def build_sdm_submission_response(
    submission,
) -> SDMSubmissionResponse | None:
    """Build an SDMSubmissionResponse from an SDMSubmission model instance."""
    if submission is None:
        return None

    status_value = (
        submission.status.value
        if hasattr(submission.status, "value")
        else str(submission.status)
    )

    drive_links = submission.drive_evidence_links or []
    if isinstance(drive_links, dict):
        # In case JSONB stores a dict instead of list
        drive_links = list(drive_links.values()) if drive_links else []

    return SDMSubmissionResponse(
        id=submission.id,
        report_id=submission.report_id,
        status=SDMSubmissionStatus(status_value),
        submitted_at=submission.submitted_at,
        attempts=submission.attempts or 0,
        error_message=submission.error_message,
        form_response_url=submission.form_response_url,
        prefill_url=submission.prefill_url,
        drive_evidence_links=drive_links,
    )
