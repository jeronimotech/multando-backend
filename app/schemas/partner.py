"""Partner schemas for the Multando API.

This module contains schemas for partner businesses, offers, and redemptions.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.schemas.base import BaseSchema


# ---------------------------------------------------------------------------
# Partner schemas
# ---------------------------------------------------------------------------


class PartnerCreate(BaseSchema):
    """Schema for submitting a partner application."""

    name: str = Field(max_length=200, description="Business name")
    description: str | None = Field(default=None, description="Business description")
    logo_url: str | None = Field(default=None, max_length=500)
    cover_image_url: str | None = Field(default=None, max_length=500)
    website_url: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=20)
    category: str = Field(default="other", description="Business category")
    address: str | None = Field(default=None, max_length=500)
    city_id: int | None = Field(default=None)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class PartnerUpdate(BaseSchema):
    """Schema for a partner updating their own profile."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None)
    logo_url: str | None = Field(default=None, max_length=500)
    cover_image_url: str | None = Field(default=None, max_length=500)
    website_url: str | None = Field(default=None, max_length=500)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=20)
    category: str | None = Field(default=None)
    address: str | None = Field(default=None, max_length=500)
    city_id: int | None = Field(default=None)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class PartnerAdminUpdate(BaseSchema):
    """Schema for admin updating partner status/tier."""

    status: str | None = Field(default=None, description="Partner status")
    tier: str | None = Field(default=None, description="Partner tier")


class PartnerResponse(BaseSchema):
    """Schema for partner in list views."""

    id: int
    name: str
    slug: str
    description: str | None = None
    logo_url: str | None = None
    cover_image_url: str | None = None
    website_url: str | None = None
    category: str
    tier: str
    status: str
    address: str | None = None
    city_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime


class OfferResponse(BaseSchema):
    """Schema for an offer in list/detail views."""

    id: int
    partner_id: int
    title: str
    description: str | None = None
    offer_type: str
    discount_value: Decimal | None = None
    multa_cost: Decimal
    original_price: Decimal | None = None
    image_url: str | None = None
    quantity_total: int | None = None
    quantity_remaining: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = True
    is_featured: bool = False
    terms: str | None = None
    created_at: datetime


class PartnerDetail(PartnerResponse):
    """Schema for detailed partner view with offers."""

    contact_email: str | None = None
    contact_phone: str | None = None
    offers: list[OfferResponse] = Field(default_factory=list)


class PartnerList(BaseSchema):
    """Schema for paginated list of partners."""

    items: list[PartnerResponse] = Field(description="List of partners")
    total: int = Field(description="Total number of partners")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")


# ---------------------------------------------------------------------------
# Offer schemas
# ---------------------------------------------------------------------------


class OfferCreate(BaseSchema):
    """Schema for creating a new offer."""

    title: str = Field(max_length=300, description="Offer title")
    description: str | None = Field(default=None, max_length=1000)
    offer_type: str = Field(description="Type of offer")
    discount_value: Decimal | None = Field(default=None)
    multa_cost: Decimal = Field(gt=0, description="MULTA tokens required")
    original_price: Decimal | None = Field(default=None)
    image_url: str | None = Field(default=None, max_length=500)
    quantity_total: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = Field(default=None)
    valid_until: datetime | None = Field(default=None)
    is_featured: bool = Field(default=False)
    terms: str | None = Field(default=None)


class OfferUpdate(BaseSchema):
    """Schema for updating an offer."""

    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=1000)
    offer_type: str | None = Field(default=None)
    discount_value: Decimal | None = Field(default=None)
    multa_cost: Decimal | None = Field(default=None, gt=0)
    original_price: Decimal | None = Field(default=None)
    image_url: str | None = Field(default=None, max_length=500)
    quantity_total: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = Field(default=None)
    valid_until: datetime | None = Field(default=None)
    is_featured: bool | None = Field(default=None)
    terms: str | None = Field(default=None)


class OfferList(BaseSchema):
    """Schema for paginated list of offers."""

    items: list[OfferResponse] = Field(description="List of offers")
    total: int = Field(description="Total number of offers")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")


# ---------------------------------------------------------------------------
# Redemption schemas
# ---------------------------------------------------------------------------


class RedemptionCreate(BaseSchema):
    """Schema for redeeming an offer (user only sends offer_id)."""

    offer_id: int = Field(description="ID of the offer to redeem")


class RedemptionConfirm(BaseSchema):
    """Schema for partner confirming a redemption by code."""

    code: str = Field(max_length=20, description="Redemption code")


class RedemptionResponse(BaseSchema):
    """Schema for redemption details."""

    id: int
    offer_id: int
    redemption_code: str
    qr_data: str | None = None
    status: str
    multa_amount: Decimal
    redeemed_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    offer: OfferResponse | None = None


class RedemptionList(BaseSchema):
    """Schema for paginated list of redemptions."""

    items: list[RedemptionResponse] = Field(description="List of redemptions")
    total: int = Field(description="Total number of redemptions")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
