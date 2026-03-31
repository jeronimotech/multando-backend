"""Model for tracking RECORD (Ministerio de Transporte) form submissions."""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class RecordSubmissionStatus(str, enum.Enum):
    """Status of a RECORD form submission."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class RecordSubmission(TimestampMixin, Base):
    """Tracks submissions of Multando reports to the RECORD form.

    Each report can have at most one RecordSubmission record. The status
    tracks whether the submission succeeded, failed, or was skipped (e.g.
    because the city is not mapped to a department).
    """

    __tablename__ = "record_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[RecordSubmissionStatus] = mapped_column(
        Enum(RecordSubmissionStatus, native_enum=False, length=20),
        default=RecordSubmissionStatus.PENDING,
        nullable=False,
        index=True,
    )

    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
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

    response_data: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Relationships
    report = relationship("Report", backref="record_submission", uselist=False)

    def __repr__(self) -> str:
        return (
            f"<RecordSubmission id={self.id} "
            f"report_id={self.report_id} "
            f"status={self.status.value}>"
        )
