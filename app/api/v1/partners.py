"""Partner endpoints for the Multando API.

This module provides endpoints for partner businesses, offers,
and MULTA token redemptions.
"""

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models.enums import PartnerStatus
from app.schemas.partner import (
    OfferCreate,
    OfferList,
    OfferResponse,
    OfferUpdate,
    PartnerAdminUpdate,
    PartnerCreate,
    PartnerDetail,
    PartnerList,
    PartnerResponse,
    PartnerUpdate,
    RedemptionConfirm,
    RedemptionCreate,
    RedemptionList,
    RedemptionResponse,
)
from app.services.partner import PartnerService

router = APIRouter(prefix="/partners", tags=["partners"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_partner_response(partner) -> PartnerResponse:
    """Build a PartnerResponse from a partner model."""
    return PartnerResponse(
        id=partner.id,
        name=partner.name,
        slug=partner.slug,
        description=partner.description,
        logo_url=partner.logo_url,
        cover_image_url=partner.cover_image_url,
        website_url=partner.website_url,
        category=partner.category.value if hasattr(partner.category, "value") else partner.category,
        tier=partner.tier.value if hasattr(partner.tier, "value") else partner.tier,
        status=partner.status.value if hasattr(partner.status, "value") else partner.status,
        address=partner.address,
        city_id=partner.city_id,
        latitude=float(partner.latitude) if partner.latitude is not None else None,
        longitude=float(partner.longitude) if partner.longitude is not None else None,
        created_at=partner.created_at,
    )


def _build_offer_response(offer) -> OfferResponse:
    """Build an OfferResponse from an offer model."""
    return OfferResponse(
        id=offer.id,
        partner_id=offer.partner_id,
        title=offer.title,
        description=offer.description,
        offer_type=offer.offer_type.value if hasattr(offer.offer_type, "value") else offer.offer_type,
        discount_value=offer.discount_value,
        multa_cost=offer.multa_cost,
        original_price=offer.original_price,
        image_url=offer.image_url,
        quantity_total=offer.quantity_total,
        quantity_remaining=offer.quantity_remaining,
        valid_from=offer.valid_from,
        valid_until=offer.valid_until,
        is_active=offer.is_active,
        is_featured=offer.is_featured,
        terms=offer.terms,
        created_at=offer.created_at,
    )


def _build_partner_detail(partner) -> PartnerDetail:
    """Build a PartnerDetail from a partner model with offers."""
    offers = []
    if hasattr(partner, "offers") and partner.offers:
        offers = [_build_offer_response(o) for o in partner.offers if o.is_active]
    return PartnerDetail(
        id=partner.id,
        name=partner.name,
        slug=partner.slug,
        description=partner.description,
        logo_url=partner.logo_url,
        cover_image_url=partner.cover_image_url,
        website_url=partner.website_url,
        contact_email=partner.contact_email,
        contact_phone=partner.contact_phone,
        category=partner.category.value if hasattr(partner.category, "value") else partner.category,
        tier=partner.tier.value if hasattr(partner.tier, "value") else partner.tier,
        status=partner.status.value if hasattr(partner.status, "value") else partner.status,
        address=partner.address,
        city_id=partner.city_id,
        latitude=float(partner.latitude) if partner.latitude is not None else None,
        longitude=float(partner.longitude) if partner.longitude is not None else None,
        created_at=partner.created_at,
        offers=offers,
    )


def _build_redemption_response(redemption, include_offer: bool = False) -> RedemptionResponse:
    """Build a RedemptionResponse from a redemption model."""
    offer_resp = None
    if include_offer and hasattr(redemption, "offer") and redemption.offer:
        offer_resp = _build_offer_response(redemption.offer)
    return RedemptionResponse(
        id=redemption.id,
        offer_id=redemption.offer_id,
        redemption_code=redemption.redemption_code,
        qr_data=redemption.qr_data,
        status=redemption.status.value if hasattr(redemption.status, "value") else redemption.status,
        multa_amount=redemption.multa_amount,
        redeemed_at=redemption.redeemed_at,
        expires_at=redemption.expires_at,
        created_at=redemption.created_at,
        offer=offer_resp,
    )


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PartnerList,
    summary="List approved partners",
)
async def list_partners(
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None, description="Filter by category"),
) -> PartnerList:
    """List approved partners with pagination."""
    svc = PartnerService(db)
    partners, total = await svc.list_partners(
        page=page, page_size=page_size, category=category
    )
    return PartnerList(
        items=[_build_partner_response(p) for p in partners],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/slug/{slug}",
    response_model=PartnerDetail,
    summary="Get partner by slug",
)
async def get_partner_by_slug(slug: str, db: DbSession) -> PartnerDetail:
    """Get partner details by URL slug."""
    svc = PartnerService(db)
    partner = await svc.get_partner_by_slug(slug)
    if not partner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    return _build_partner_detail(partner)


@router.get(
    "/{partner_id}",
    response_model=PartnerDetail,
    summary="Get partner detail",
)
async def get_partner(partner_id: int, db: DbSession) -> PartnerDetail:
    """Get partner details with active offers."""
    svc = PartnerService(db)
    partner = await svc.get_partner(partner_id)
    if not partner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    return _build_partner_detail(partner)


@router.get(
    "/{partner_id}/offers",
    response_model=OfferList,
    summary="List partner offers",
)
async def list_partner_offers(
    partner_id: int,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> OfferList:
    """List active offers for a specific partner."""
    svc = PartnerService(db)
    offers, total = await svc.list_offers(
        partner_id=partner_id, active_only=True, page=page, page_size=page_size
    )
    return OfferList(
        items=[_build_offer_response(o) for o in offers],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Authenticated user endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/apply",
    response_model=PartnerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply to become a partner",
)
async def apply_partner(
    data: PartnerCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> PartnerResponse:
    """Submit a partner application."""
    svc = PartnerService(db)
    # Check if user already has a partner application
    existing = await svc.get_partner_by_user(current_user.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a partner application",
        )
    partner = await svc.apply(data, current_user.id)
    return _build_partner_response(partner)


@router.post(
    "/offers/{offer_id}/redeem",
    response_model=RedemptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Redeem an offer",
)
async def redeem_offer(
    offer_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> RedemptionResponse:
    """Redeem an offer by spending MULTA tokens."""
    svc = PartnerService(db)
    try:
        redemption = await svc.redeem_offer(offer_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_redemption_response(redemption)


@router.get(
    "/my/redemptions",
    response_model=RedemptionList,
    summary="My redemptions",
)
async def list_my_redemptions(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> RedemptionList:
    """List the current user's redemption history."""
    svc = PartnerService(db)
    redemptions, total = await svc.list_user_redemptions(
        current_user.id, page=page, page_size=page_size
    )
    return RedemptionList(
        items=[_build_redemption_response(r, include_offer=True) for r in redemptions],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# Partner owner endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/my/partner",
    response_model=PartnerDetail,
    summary="Get my partner profile",
)
async def get_my_partner(
    current_user: CurrentUser,
    db: DbSession,
) -> PartnerDetail:
    """Get the current user's own partner profile."""
    svc = PartnerService(db)
    partner = await svc.get_partner_by_user(current_user.id)
    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not have a partner profile",
        )
    return _build_partner_detail(partner)


@router.put(
    "/my/partner",
    response_model=PartnerResponse,
    summary="Update my partner profile",
)
async def update_my_partner(
    data: PartnerUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> PartnerResponse:
    """Update the current user's own partner profile."""
    svc = PartnerService(db)
    partner = await svc.get_partner_by_user(current_user.id)
    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not have a partner profile",
        )
    try:
        updated = await svc.update_partner(partner.id, data, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_partner_response(updated)


@router.post(
    "/my/offers",
    response_model=OfferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an offer",
)
async def create_offer(
    data: OfferCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> OfferResponse:
    """Create a new offer for the current user's partner."""
    svc = PartnerService(db)
    partner = await svc.get_partner_by_user(current_user.id)
    if not partner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You do not have a partner profile",
        )
    try:
        offer = await svc.create_offer(partner.id, data, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_offer_response(offer)


@router.put(
    "/my/offers/{offer_id}",
    response_model=OfferResponse,
    summary="Update an offer",
)
async def update_offer(
    offer_id: int,
    data: OfferUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> OfferResponse:
    """Update an offer owned by the current user's partner."""
    svc = PartnerService(db)
    try:
        offer = await svc.update_offer(offer_id, data, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_offer_response(offer)


@router.delete(
    "/my/offers/{offer_id}",
    response_model=OfferResponse,
    summary="Deactivate an offer",
)
async def deactivate_offer(
    offer_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> OfferResponse:
    """Deactivate (soft-delete) an offer."""
    svc = PartnerService(db)
    try:
        offer = await svc.deactivate_offer(offer_id, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_offer_response(offer)


@router.post(
    "/my/redemptions/confirm",
    response_model=RedemptionResponse,
    summary="Confirm a redemption",
)
async def confirm_redemption(
    data: RedemptionConfirm,
    current_user: CurrentUser,
    db: DbSession,
) -> RedemptionResponse:
    """Partner confirms a redemption code as used."""
    svc = PartnerService(db)
    try:
        redemption = await svc.confirm_redemption(data.code, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_redemption_response(redemption)


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/admin/pending",
    response_model=PartnerList,
    summary="List pending partner applications",
)
async def list_pending_partners(
    admin_user: AdminUser,
    db: DbSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PartnerList:
    """List pending partner applications (admin only)."""
    svc = PartnerService(db)
    partners, total = await svc.list_pending(page=page, page_size=page_size)
    return PartnerList(
        items=[_build_partner_response(p) for p in partners],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put(
    "/admin/{partner_id}",
    response_model=PartnerResponse,
    summary="Admin update partner",
)
async def admin_update_partner(
    partner_id: int,
    data: PartnerAdminUpdate,
    admin_user: AdminUser,
    db: DbSession,
) -> PartnerResponse:
    """Admin approves/rejects partner or changes tier."""
    svc = PartnerService(db)
    try:
        partner = await svc.admin_update_partner(partner_id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return _build_partner_response(partner)
