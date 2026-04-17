"""Partner service for managing business partnerships and offer redemptions."""

import logging
import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.activity import Activity
from app.models.enums import (
    ActivityType,
    OfferType,
    PartnerCategory,
    PartnerStatus,
    PartnerTier,
    RedemptionStatus,
)
from app.models.partner import OfferRedemption, Partner, PartnerOffer
from app.models.wallet import HotWalletLedger
from app.schemas.partner import (
    OfferCreate,
    OfferUpdate,
    PartnerAdminUpdate,
    PartnerCreate,
    PartnerUpdate,
)

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a business name."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def _generate_redemption_code() -> str:
    """Generate an 8-character alphanumeric redemption code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(8))


class PartnerService:
    """Service for handling partner operations, offers, and redemptions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Partner management
    # ------------------------------------------------------------------

    async def apply(self, data: PartnerCreate, user_id: UUID) -> Partner:
        """Submit a new partner application.

        Args:
            data: Partner application data.
            user_id: UUID of the applying user (business owner).

        Returns:
            The newly created Partner with status=pending.
        """
        slug = _slugify(data.name)
        # Ensure slug uniqueness
        base_slug = slug
        counter = 1
        while True:
            existing = await self.db.execute(
                select(Partner).where(Partner.slug == slug)
            )
            if existing.scalar_one_or_none() is None:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        partner = Partner(
            user_id=user_id,
            name=data.name,
            slug=slug,
            description=data.description,
            logo_url=data.logo_url,
            cover_image_url=data.cover_image_url,
            website_url=data.website_url,
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            category=PartnerCategory(data.category),
            tier=PartnerTier.COMMUNITY,
            status=PartnerStatus.PENDING,
            address=data.address,
            city_id=data.city_id,
            latitude=data.latitude,
            longitude=data.longitude,
        )
        self.db.add(partner)
        await self.db.flush()
        await self.db.refresh(partner)
        return partner

    async def list_partners(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        status: PartnerStatus = PartnerStatus.APPROVED,
    ) -> tuple[list[Partner], int]:
        """List partners with pagination and optional filters.

        Args:
            page: Page number (1-indexed).
            page_size: Items per page.
            category: Optional category filter.
            status: Partner status filter (default: approved).

        Returns:
            Tuple of (partners list, total count).
        """
        query = select(Partner).where(Partner.status == status)
        if category:
            query = query.where(Partner.category == PartnerCategory(category))

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Partner.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        partners = list(result.scalars().all())
        return partners, total

    async def get_partner(self, partner_id: int) -> Partner | None:
        """Get a partner by ID with offers loaded."""
        result = await self.db.execute(
            select(Partner)
            .options(selectinload(Partner.offers))
            .where(Partner.id == partner_id)
        )
        return result.scalar_one_or_none()

    async def get_partner_by_slug(self, slug: str) -> Partner | None:
        """Get a partner by slug with offers loaded."""
        result = await self.db.execute(
            select(Partner)
            .options(selectinload(Partner.offers))
            .where(Partner.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_partner_by_user(self, user_id: UUID) -> Partner | None:
        """Get the partner owned by a specific user."""
        result = await self.db.execute(
            select(Partner)
            .options(selectinload(Partner.offers))
            .where(Partner.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_partner(
        self, partner_id: int, data: PartnerUpdate, user_id: UUID
    ) -> Partner:
        """Update partner profile (owner only).

        Raises:
            ValueError: If partner not found or user is not the owner.
        """
        partner = await self.get_partner(partner_id)
        if not partner:
            raise ValueError("Partner not found")
        if partner.user_id != user_id:
            raise ValueError("Only the partner owner can update the profile")

        update_data = data.model_dump(exclude_unset=True)
        if "category" in update_data and update_data["category"] is not None:
            update_data["category"] = PartnerCategory(update_data["category"])
        for field, value in update_data.items():
            setattr(partner, field, value)

        await self.db.flush()
        await self.db.refresh(partner)
        return partner

    async def admin_update_partner(
        self, partner_id: int, data: PartnerAdminUpdate
    ) -> Partner:
        """Admin update partner status/tier.

        Raises:
            ValueError: If partner not found.
        """
        partner = await self.get_partner(partner_id)
        if not partner:
            raise ValueError("Partner not found")

        if data.status is not None:
            partner.status = PartnerStatus(data.status)
        if data.tier is not None:
            partner.tier = PartnerTier(data.tier)

        await self.db.flush()
        await self.db.refresh(partner)
        return partner

    async def list_pending(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Partner], int]:
        """List pending partner applications (admin use)."""
        return await self.list_partners(
            page=page, page_size=page_size, status=PartnerStatus.PENDING
        )

    # ------------------------------------------------------------------
    # Offer management
    # ------------------------------------------------------------------

    async def create_offer(
        self, partner_id: int, data: OfferCreate, user_id: UUID
    ) -> PartnerOffer:
        """Create a new offer for a partner.

        Raises:
            ValueError: If partner not found or user is not the owner.
        """
        partner = await self.get_partner(partner_id)
        if not partner:
            raise ValueError("Partner not found")
        if partner.user_id != user_id:
            raise ValueError("Only the partner owner can create offers")
        if partner.status != PartnerStatus.APPROVED:
            raise ValueError("Partner must be approved to create offers")

        offer = PartnerOffer(
            partner_id=partner_id,
            title=data.title,
            description=data.description,
            offer_type=OfferType(data.offer_type),
            discount_value=data.discount_value,
            multa_cost=data.multa_cost,
            original_price=data.original_price,
            image_url=data.image_url,
            quantity_total=data.quantity_total,
            quantity_remaining=data.quantity_total,  # start full
            valid_from=data.valid_from,
            valid_until=data.valid_until,
            is_featured=data.is_featured,
            terms=data.terms,
        )
        self.db.add(offer)
        await self.db.flush()
        await self.db.refresh(offer)
        return offer

    async def list_offers(
        self,
        partner_id: int | None = None,
        active_only: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PartnerOffer], int]:
        """List offers with pagination.

        Args:
            partner_id: Optional filter by partner.
            active_only: Only return active offers.
            page: Page number.
            page_size: Items per page.

        Returns:
            Tuple of (offers list, total count).
        """
        query = select(PartnerOffer)
        if partner_id is not None:
            query = query.where(PartnerOffer.partner_id == partner_id)
        if active_only:
            query = query.where(PartnerOffer.is_active.is_(True))
            # Only return offers from approved partners
            query = query.join(Partner).where(Partner.status == PartnerStatus.APPROVED)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(PartnerOffer.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        offers = list(result.scalars().all())
        return offers, total

    async def get_offer(self, offer_id: int) -> PartnerOffer | None:
        """Get a single offer by ID."""
        result = await self.db.execute(
            select(PartnerOffer)
            .options(selectinload(PartnerOffer.partner))
            .where(PartnerOffer.id == offer_id)
        )
        return result.scalar_one_or_none()

    async def update_offer(
        self, offer_id: int, data: OfferUpdate, user_id: UUID
    ) -> PartnerOffer:
        """Update an offer (partner owner only).

        Raises:
            ValueError: If offer not found or user is not the partner owner.
        """
        offer = await self.get_offer(offer_id)
        if not offer:
            raise ValueError("Offer not found")

        partner = await self.get_partner(offer.partner_id)
        if not partner or partner.user_id != user_id:
            raise ValueError("Only the partner owner can update offers")

        update_data = data.model_dump(exclude_unset=True)
        if "offer_type" in update_data and update_data["offer_type"] is not None:
            update_data["offer_type"] = OfferType(update_data["offer_type"])
        for field, value in update_data.items():
            setattr(offer, field, value)

        await self.db.flush()
        await self.db.refresh(offer)
        return offer

    async def deactivate_offer(self, offer_id: int, user_id: UUID) -> PartnerOffer:
        """Deactivate an offer (soft delete).

        Raises:
            ValueError: If offer not found or user is not the partner owner.
        """
        offer = await self.get_offer(offer_id)
        if not offer:
            raise ValueError("Offer not found")

        partner = await self.get_partner(offer.partner_id)
        if not partner or partner.user_id != user_id:
            raise ValueError("Only the partner owner can deactivate offers")

        offer.is_active = False
        await self.db.flush()
        await self.db.refresh(offer)
        return offer

    # ------------------------------------------------------------------
    # Redemption
    # ------------------------------------------------------------------

    async def redeem_offer(self, offer_id: int, user_id: UUID) -> OfferRedemption:
        """Redeem an offer by spending MULTA tokens.

        Steps:
            1. Verify offer is active, not expired, has quantity
            2. Check user has enough MULTA in HotWalletLedger
            3. Deduct MULTA (atomic)
            4. Decrement quantity_remaining (atomic)
            5. Generate redemption code
            6. Create OfferRedemption
            7. Log Activity
            8. Return redemption

        Raises:
            ValueError: On any validation failure.
        """
        now = datetime.now(timezone.utc)

        # 1. Load and validate offer
        offer = await self.get_offer(offer_id)
        if not offer:
            raise ValueError("Offer not found")
        if not offer.is_active:
            raise ValueError("Offer is no longer active")
        if offer.valid_until and offer.valid_until < now:
            raise ValueError("Offer has expired")
        if offer.valid_from and offer.valid_from > now:
            raise ValueError("Offer is not yet available")
        if offer.quantity_remaining is not None and offer.quantity_remaining <= 0:
            raise ValueError("Offer is sold out")

        multa_cost = offer.multa_cost

        # 2. Check user balance in HotWalletLedger
        ledger_result = await self.db.execute(
            select(HotWalletLedger).where(HotWalletLedger.user_id == user_id)
        )
        ledger = ledger_result.scalar_one_or_none()
        if not ledger or ledger.balance < multa_cost:
            raise ValueError("Insufficient MULTA balance")

        # 3. Deduct MULTA atomically
        rows = await self.db.execute(
            update(HotWalletLedger)
            .where(
                HotWalletLedger.user_id == user_id,
                HotWalletLedger.balance >= multa_cost,
            )
            .values(balance=HotWalletLedger.balance - multa_cost)
            .returning(HotWalletLedger.balance)
        )
        updated_balance = rows.scalar_one_or_none()
        if updated_balance is None:
            raise ValueError("Insufficient MULTA balance (concurrent deduction)")

        # 4. Decrement quantity atomically (if limited)
        if offer.quantity_remaining is not None:
            qty_result = await self.db.execute(
                update(PartnerOffer)
                .where(
                    PartnerOffer.id == offer_id,
                    PartnerOffer.quantity_remaining > 0,
                )
                .values(quantity_remaining=PartnerOffer.quantity_remaining - 1)
                .returning(PartnerOffer.quantity_remaining)
            )
            new_qty = qty_result.scalar_one_or_none()
            if new_qty is None:
                # Rollback MULTA deduction — re-credit
                await self.db.execute(
                    update(HotWalletLedger)
                    .where(HotWalletLedger.user_id == user_id)
                    .values(balance=HotWalletLedger.balance + multa_cost)
                )
                raise ValueError("Offer is sold out (concurrent redemption)")

        # 5. Generate unique redemption code
        code = _generate_redemption_code()
        # Quick collision check (extremely unlikely with 8 alphanum chars)
        existing = await self.db.execute(
            select(OfferRedemption).where(OfferRedemption.redemption_code == code)
        )
        while existing.scalar_one_or_none() is not None:
            code = _generate_redemption_code()
            existing = await self.db.execute(
                select(OfferRedemption).where(OfferRedemption.redemption_code == code)
            )

        qr_data = f"MULTA-REDEEM:{code}"

        # 6. Create redemption record
        redemption = OfferRedemption(
            user_id=user_id,
            offer_id=offer_id,
            redemption_code=code,
            qr_data=qr_data,
            status=RedemptionStatus.PENDING,
            multa_amount=multa_cost,
            expires_at=now + timedelta(days=7),
        )
        self.db.add(redemption)
        await self.db.flush()

        # 7. Log activity
        activity = Activity(
            user_id=user_id,
            type=ActivityType.OFFER_REDEEMED,
            points_earned=0,
            multa_earned=-multa_cost,  # negative = spent
            reference_type="offer_redemption",
            reference_id=str(redemption.id),
            activity_metadata={
                "offer_id": offer_id,
                "offer_title": offer.title,
                "partner_id": offer.partner_id,
                "multa_cost": str(multa_cost),
                "redemption_code": code,
            },
        )
        self.db.add(activity)
        await self.db.flush()

        # 8. Return
        await self.db.refresh(redemption)
        return redemption

    async def confirm_redemption(
        self, code: str, partner_user_id: UUID
    ) -> OfferRedemption:
        """Partner confirms a redemption as used.

        Args:
            code: The redemption code.
            partner_user_id: UUID of the partner owner confirming.

        Raises:
            ValueError: If code not found, already used, or user not the partner owner.
        """
        result = await self.db.execute(
            select(OfferRedemption)
            .options(selectinload(OfferRedemption.offer).selectinload(PartnerOffer.partner))
            .where(OfferRedemption.redemption_code == code)
        )
        redemption = result.scalar_one_or_none()
        if not redemption:
            raise ValueError("Redemption code not found")

        partner = redemption.offer.partner
        if partner.user_id != partner_user_id:
            raise ValueError("Only the partner owner can confirm redemptions")

        if redemption.status == RedemptionStatus.USED:
            raise ValueError("Redemption has already been used")
        if redemption.status == RedemptionStatus.CANCELLED:
            raise ValueError("Redemption has been cancelled")
        if redemption.status == RedemptionStatus.EXPIRED:
            raise ValueError("Redemption has expired")

        now = datetime.now(timezone.utc)
        if redemption.expires_at and redemption.expires_at < now:
            redemption.status = RedemptionStatus.EXPIRED
            await self.db.flush()
            raise ValueError("Redemption has expired")

        redemption.status = RedemptionStatus.USED
        redemption.redeemed_at = now
        await self.db.flush()
        await self.db.refresh(redemption)
        return redemption

    async def list_user_redemptions(
        self, user_id: UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[OfferRedemption], int]:
        """List redemptions for a user."""
        query = (
            select(OfferRedemption)
            .options(selectinload(OfferRedemption.offer))
            .where(OfferRedemption.user_id == user_id)
        )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(OfferRedemption.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        redemptions = list(result.scalars().all())
        return redemptions, total
