"""Admin service for super-admin and authority-admin operations.

Handles authority CRUD, staff management, city management, and dashboard stats.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Authority,
    AuthorityUser,
    City,
    Report,
    User,
)
from app.models.enums import (
    AuthorityRole,
    ReportStatus,
    SubscriptionTier,
    UserRole,
)


class AdminService:
    """Service for admin-level operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Authority CRUD
    # ------------------------------------------------------------------

    async def create_authority(
        self,
        name: str,
        code: str,
        city_id: int,
        country: str = "DO",
        contact_email: str | None = None,
        contact_name: str | None = None,
        subscription_tier: SubscriptionTier = SubscriptionTier.FREE,
    ) -> tuple[Authority, str]:
        """Create a new authority and return the one-time API key.

        Returns:
            Tuple of (Authority, plaintext_api_key).
        """
        api_key = f"mlt_{secrets.token_urlsafe(32)}"
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        authority = Authority(
            name=name,
            code=code,
            city_id=city_id,
            country=country,
            contact_email=contact_email,
            contact_name=contact_name,
            api_key_hash=api_key_hash,
            subscription_tier=subscription_tier,
        )
        self.db.add(authority)
        await self.db.commit()
        await self.db.refresh(authority, attribute_names=["city_rel", "users"])
        return authority, api_key

    async def list_authorities(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Authority], int]:
        """Return a paginated list of authorities with staff counts."""
        count_q = select(func.count()).select_from(Authority)
        total = (await self.db.execute(count_q)).scalar() or 0

        offset = (page - 1) * page_size
        q = (
            select(Authority)
            .options(selectinload(Authority.users))
            .order_by(Authority.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(q)
        return list(result.scalars().all()), total

    async def get_authority_detail(self, authority_id: int) -> Authority | None:
        """Get a single authority with eagerly loaded staff and city."""
        q = (
            select(Authority)
            .options(
                selectinload(Authority.users).selectinload(AuthorityUser.user),
                selectinload(Authority.city_rel),
            )
            .where(Authority.id == authority_id)
        )
        result = await self.db.execute(q)
        return result.scalar_one_or_none()

    async def update_authority(
        self, authority_id: int, updates: dict
    ) -> Authority | None:
        """Update authority fields. Returns None if not found."""
        authority = await self.db.get(Authority, authority_id)
        if not authority:
            return None
        for key, value in updates.items():
            if value is not None and hasattr(authority, key):
                setattr(authority, key, value)
        await self.db.commit()
        await self.db.refresh(authority)
        return authority

    async def deactivate_authority(self, authority_id: int) -> Authority | None:
        """Soft-deactivate an authority by clearing its API key hash.

        We don't hard-delete to preserve data integrity.
        """
        authority = await self.db.get(Authority, authority_id)
        if not authority:
            return None
        authority.api_key_hash = None
        await self.db.commit()
        await self.db.refresh(authority)
        return authority

    # ------------------------------------------------------------------
    # Staff management
    # ------------------------------------------------------------------

    async def add_staff_to_authority(
        self, authority_id: int, email: str, role: AuthorityRole
    ) -> AuthorityUser:
        """Add a user to an authority.  Creates the user if they don't exist.

        Returns:
            The created AuthorityUser record.
        """
        # Find or create user
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                email=email,
                role=UserRole.AUTHORITY,
                is_active=True,
            )
            self.db.add(user)
            await self.db.flush()
        elif user.role == UserRole.CITIZEN:
            user.role = UserRole.AUTHORITY

        # Check for existing membership
        existing = await self.db.execute(
            select(AuthorityUser).where(
                AuthorityUser.authority_id == authority_id,
                AuthorityUser.user_id == user.id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("User is already a member of this authority")

        authority_user = AuthorityUser(
            authority_id=authority_id,
            user_id=user.id,
            role=role,
        )
        self.db.add(authority_user)
        await self.db.commit()
        await self.db.refresh(authority_user, attribute_names=["user"])
        return authority_user

    async def remove_staff(self, authority_id: int, user_id: UUID) -> bool:
        """Remove a user from an authority. Returns True if removed."""
        result = await self.db.execute(
            select(AuthorityUser).where(
                AuthorityUser.authority_id == authority_id,
                AuthorityUser.user_id == user_id,
            )
        )
        au = result.scalar_one_or_none()
        if not au:
            return False
        await self.db.delete(au)
        await self.db.commit()
        return True

    async def update_staff_role(
        self, authority_id: int, user_id: UUID, role: AuthorityRole
    ) -> AuthorityUser | None:
        """Update a staff member's role within an authority."""
        result = await self.db.execute(
            select(AuthorityUser).where(
                AuthorityUser.authority_id == authority_id,
                AuthorityUser.user_id == user_id,
            )
        )
        au = result.scalar_one_or_none()
        if not au:
            return None
        au.role = role
        await self.db.commit()
        await self.db.refresh(au)
        return au

    # ------------------------------------------------------------------
    # City management (Super Admin)
    # ------------------------------------------------------------------

    async def create_city(
        self,
        name: str,
        country_code: str,
        latitude: float,
        longitude: float,
        state_province: str | None = None,
        timezone: str = "UTC",
    ) -> City:
        city = City(
            name=name,
            country_code=country_code,
            state_province=state_province,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
        )
        self.db.add(city)
        await self.db.commit()
        await self.db.refresh(city)
        return city

    async def update_city(self, city_id: int, updates: dict) -> City | None:
        city = await self.db.get(City, city_id)
        if not city:
            return None
        for key, value in updates.items():
            if value is not None and hasattr(city, key):
                setattr(city, key, value)
        await self.db.commit()
        await self.db.refresh(city)
        return city

    async def deactivate_city(self, city_id: int) -> City | None:
        city = await self.db.get(City, city_id)
        if not city:
            return None
        city.is_active = False
        await self.db.commit()
        await self.db.refresh(city)
        return city

    # ------------------------------------------------------------------
    # Platform stats (Super Admin)
    # ------------------------------------------------------------------

    async def get_platform_stats(self) -> dict:
        """Return platform-wide statistics."""
        now = datetime.now(timezone.utc)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_users = (
            await self.db.execute(select(func.count()).select_from(User))
        ).scalar() or 0

        total_reports = (
            await self.db.execute(select(func.count()).select_from(Report))
        ).scalar() or 0

        total_authorities = (
            await self.db.execute(select(func.count()).select_from(Authority))
        ).scalar() or 0

        total_cities = (
            await self.db.execute(
                select(func.count()).select_from(City).where(City.is_active.is_(True))
            )
        ).scalar() or 0

        reports_today = (
            await self.db.execute(
                select(func.count())
                .select_from(Report)
                .where(Report.created_at >= start_of_today)
            )
        ).scalar() or 0

        reports_this_month = (
            await self.db.execute(
                select(func.count())
                .select_from(Report)
                .where(Report.created_at >= start_of_month)
            )
        ).scalar() or 0

        return {
            "total_users": total_users,
            "total_reports": total_reports,
            "total_authorities": total_authorities,
            "total_cities": total_cities,
            "reports_today": reports_today,
            "reports_this_month": reports_this_month,
        }

    # ------------------------------------------------------------------
    # Authority dashboard
    # ------------------------------------------------------------------

    async def get_authority_dashboard(self, authority: Authority) -> dict:
        """Return dashboard stats scoped to an authority's city."""
        if authority.city_id:
            base_filter = Report.city_id == authority.city_id
        else:
            base_filter = Report.location_country == authority.country

        # Total
        total = (
            await self.db.execute(
                select(func.count()).select_from(Report).where(base_filter)
            )
        ).scalar() or 0

        # By status
        status_rows = await self.db.execute(
            select(Report.status, func.count())
            .where(base_filter)
            .group_by(Report.status)
        )
        by_status = {row[0].value: row[1] for row in status_rows}

        # Recent reports (last 10)
        recent_q = (
            select(Report)
            .where(base_filter)
            .order_by(Report.created_at.desc())
            .limit(10)
        )
        recent_rows = await self.db.execute(recent_q)
        recent_reports = [
            {
                "id": str(r.id),
                "short_id": r.short_id,
                "status": r.status.value,
                "created_at": r.created_at.isoformat(),
            }
            for r in recent_rows.scalars().all()
        ]

        # Top infractions
        infraction_rows = await self.db.execute(
            select(Report.infraction_id, func.count())
            .where(base_filter)
            .group_by(Report.infraction_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_infractions = [
            {"infraction_id": row[0], "count": row[1]} for row in infraction_rows
        ]

        # Verification rate
        verified = by_status.get(ReportStatus.VERIFIED.value, 0)
        verification_rate = (verified / total * 100) if total > 0 else 0.0

        return {
            "total_reports": total,
            "reports_by_status": by_status,
            "recent_reports": recent_reports,
            "top_infractions": top_infractions,
            "verification_rate": round(verification_rate, 2),
        }
