"""Model for tracking SDM (Secretaría Distrital de Movilidad) Bogota submissions."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SDMSubmissionStatus(str, enum.Enum):
    """Status of an SDM Google Form submission."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class SDMSubmission(TimestampMixin, Base):
    """Tracks submissions of Bogota reports to the SDM Google Form.

    Each report can have at most one SDMSubmission record. The status
    tracks whether the submission succeeded, failed, or was skipped
    (e.g. because the report is not in Bogota).
    """

    __tablename__ = "sdm_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[SDMSubmissionStatus] = mapped_column(
        Enum(SDMSubmissionStatus, native_enum=False, length=20),
        default=SDMSubmissionStatus.PENDING,
        nullable=False,
        index=True,
    )

    form_response_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    prefill_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    drive_evidence_links: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    report = relationship("Report", backref="sdm_submission", uselist=False)

    def __repr__(self) -> str:
        return (
            f"<SDMSubmission id={self.id} "
            f"report_id={self.report_id} "
            f"status={self.status.value}>"
        )
