"""Partner-related models: Partner, PartnerOffer, OfferRedemption."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
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
    OfferType,
    PartnerCategory,
    PartnerStatus,
    PartnerTier,
    RedemptionStatus,
)

if TYPE_CHECKING:
    from app.models.city import City
    from app.models.user import User


class Partner(TimestampMixin, Base):
    """Local business partner that offers rewards to MULTA token holders."""

    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cover_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    category: Mapped[PartnerCategory] = mapped_column(
        default=PartnerCategory.OTHER, nullable=False
    )
    tier: Mapped[PartnerTier] = mapped_column(
        default=PartnerTier.COMMUNITY, nullable=False
    )
    status: Mapped[PartnerStatus] = mapped_column(
        default=PartnerStatus.PENDING, nullable=False, index=True
    )
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("cities.id", ondelete="SET NULL"), nullable=True
    )
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    partner_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    offers: Mapped[list["PartnerOffer"]] = relationship(
        "PartnerOffer", back_populates="partner", cascade="all, delete-orphan"
    )
    city: Mapped[Optional["City"]] = relationship("City")
    user: Mapped[Optional["User"]] = relationship("User")


class PartnerOffer(TimestampMixin, Base):
    """An offer/deal from a partner that users can redeem with MULTA tokens."""

    __tablename__ = "partner_offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("partners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    offer_type: Mapped[OfferType] = mapped_column(nullable=False)
    discount_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    multa_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    original_price: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    quantity_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quantity_remaining: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    partner: Mapped["Partner"] = relationship("Partner", back_populates="offers")
    redemptions: Mapped[list["OfferRedemption"]] = relationship(
        "OfferRedemption", back_populates="offer", cascade="all, delete-orphan"
    )


class OfferRedemption(TimestampMixin, Base):
    """Record of a user redeeming a partner offer with MULTA tokens."""

    __tablename__ = "offer_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("partner_offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    redemption_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    qr_data: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[RedemptionStatus] = mapped_column(
        default=RedemptionStatus.PENDING, nullable=False, index=True
    )
    multa_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    offer: Mapped["PartnerOffer"] = relationship("PartnerOffer", back_populates="redemptions")
