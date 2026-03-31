"""City model for multi-tenancy support."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.authority import Authority
    from app.models.report import Report


class City(Base):
    """City entity for location-based multi-tenancy.

    Each city represents a jurisdiction where reports can be filed
    and authorities can operate. Cities are uniquely identified by
    name + country_code combination.
    """

    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("name", "country_code", name="uq_city_name_country"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    state_province: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=func.now(), nullable=False
    )

    # Relationships
    authorities: Mapped[list["Authority"]] = relationship(
        "Authority", back_populates="city_rel"
    )
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="city_rel"
    )

    def __repr__(self) -> str:
        return f"<City {self.name} ({self.country_code})>"
