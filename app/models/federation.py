"""Federation models for cross-instance data sharing.

Stores anonymized reports received from federated self-hosted instances
and tracks registered federation instances.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FederatedReport(Base):
    """Anonymized report received from a federated instance."""

    __tablename__ = "federated_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    instance_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    report_short_id: Mapped[str] = mapped_column(String(20), nullable=False)
    infraction_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    infraction_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    vehicle_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country_code: Mapped[str] = mapped_column(String(5), default="CO")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latitude_approx: Mapped[float | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    longitude_approx: Mapped[float | None] = mapped_column(
        Numeric(8, 4), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )


class FederationInstance(Base):
    """A registered self-hosted instance that syncs to the hub."""

    __tablename__ = "federation_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    city: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str] = mapped_column(String(5), default="CO")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_reports_synced: Mapped[int] = mapped_column(Integer, default=0)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
