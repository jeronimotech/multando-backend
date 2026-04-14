"""Report-related models: Report, Evidence, Infraction, VehicleType."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    EvidenceType,
    InfractionCategory,
    InfractionSeverity,
    ReportSource,
    ReportStatus,
    VehicleCategory,
)

if TYPE_CHECKING:
    from app.models.city import City
    from app.models.user import User


class Infraction(Base):
    """Types of traffic infractions that can be reported."""

    __tablename__ = "infractions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    name_es: Mapped[str] = mapped_column(String(200), nullable=False)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_es: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[InfractionCategory] = mapped_column(nullable=False)
    severity: Mapped[InfractionSeverity] = mapped_column(
        default=InfractionSeverity.MEDIUM, nullable=False
    )
    points_reward: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    multa_reward: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("1.000000"), nullable=False
    )
    icon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="infraction")


class VehicleType(Base):
    """Types of vehicles that can be reported."""

    __tablename__ = "vehicle_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    name_es: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    plate_pattern: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    requires_plate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="vehicle_type"
    )


class Report(TimestampMixin, Base):
    """Traffic violation report submitted by users."""

    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    short_id: Mapped[str] = mapped_column(
        String(12), unique=True, nullable=False, index=True
    )

    # Reporter
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[ReportSource] = mapped_column(
        default=ReportSource.MOBILE, nullable=False
    )

    # Infraction details
    infraction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("infractions.id", ondelete="RESTRICT"), nullable=False
    )

    # Vehicle details
    vehicle_plate: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True
    )
    vehicle_type_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("vehicle_types.id", ondelete="SET NULL"), nullable=True
    )
    vehicle_category: Mapped[VehicleCategory] = mapped_column(
        default=VehicleCategory.PRIVATE, nullable=False
    )

    # Location
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    location_city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str] = mapped_column(
        String(2), default="DO", nullable=False
    )
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("cities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Incident timing
    incident_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Verification status
    status: Mapped[ReportStatus] = mapped_column(
        default=ReportStatus.PENDING, nullable=False, index=True
    )
    verifier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Blockchain
    on_chain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tx_signature: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Confidence scoring (computed by ConfidenceScorer service)
    confidence_score: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False
    )
    confidence_factors: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )

    # Community voting counters (used by verification flow)
    verification_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    rejection_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Authority validation (for comparendo flow)
    authority_validator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    authority_validated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    authority_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    reporter: Mapped["User"] = relationship(
        "User", back_populates="reports", foreign_keys=[reporter_id]
    )
    verifier: Mapped[Optional["User"]] = relationship(
        "User", back_populates="verified_reports", foreign_keys=[verifier_id]
    )
    authority_validator: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[authority_validator_id]
    )
    infraction: Mapped["Infraction"] = relationship(
        "Infraction", back_populates="reports"
    )
    vehicle_type: Mapped[Optional["VehicleType"]] = relationship(
        "VehicleType", back_populates="reports"
    )
    city_rel: Mapped[Optional["City"]] = relationship(
        "City", back_populates="reports"
    )
    evidences: Mapped[list["Evidence"]] = relationship(
        "Evidence", back_populates="report", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Report {self.short_id} ({self.status.value})>"


class Evidence(Base):
    """Evidence files attached to reports."""

    __tablename__ = "evidences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[EvidenceType] = mapped_column(nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    ipfs_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Secure Evidence Capture fields
    capture_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )  # SHA-256 hex
    capture_signature: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    capture_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # metadata schema: {device_id, motion_verified, capture_method, platform,
    #                   app_version, gps_accuracy}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="evidences")

    def __repr__(self) -> str:
        return f"<Evidence {self.id} ({self.type.value})>"
