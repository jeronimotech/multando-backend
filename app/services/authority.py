"""Authority service for B2B API operations.

This module contains business logic for authority (government/regulatory body) operations.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Authority, Report
from app.models.city import City
from app.models.enums import ReportStatus, SubscriptionTier


class AuthorityService:
    """Service for authority-related operations."""

    def __init__(self, db: AsyncSession):
        """Initialize the service with a database session.

        Args:
            db: Async database session.
        """
        self.db = db

    async def create_authority(
        self,
        name: str,
        code: str,
        country: str,
        city: str | None,
        contact_email: str,
        contact_name: str,
    ) -> tuple[Authority, str]:
        """Create a new authority and return API key.

        Args:
            name: Authority name.
            code: Unique authority code.
            country: ISO 3166-1 alpha-2 country code.
            city: Optional city name.
            contact_email: Contact email address.
            contact_name: Contact person name.

        Returns:
            Tuple of (Authority, api_key). API key is only returned once.
        """
        # Generate API key
        api_key = f"mlt_{secrets.token_urlsafe(32)}"
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        authority = Authority(
            name=name,
            code=code,
            country=country,
            city=city,
            contact_email=contact_email,
            contact_name=contact_name,
            api_key_hash=api_key_hash,
            subscription_tier=SubscriptionTier.FREE,
        )
        self.db.add(authority)
        await self.db.commit()
        await self.db.refresh(authority)

        return authority, api_key

    async def get_by_code(self, code: str) -> Authority | None:
        """Get authority by code.

        Args:
            code: Unique authority code.

        Returns:
            Authority if found, None otherwise.
        """
        result = await self.db.execute(
            select(Authority).where(Authority.code == code)
        )
        return result.scalar_one_or_none()

    async def validate_api_key(self, api_key: str) -> Authority | None:
        """Validate API key and return authority.

        Args:
            api_key: The API key to validate.

        Returns:
            Authority if valid, None otherwise.
        """
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        result = await self.db.execute(
            select(Authority).where(Authority.api_key_hash == api_key_hash)
        )
        return result.scalar_one_or_none()

    async def get_reports(
        self,
        authority: Authority,
        page: int = 1,
        page_size: int = 50,
        status: ReportStatus | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[Report], int]:
        """Get reports for authority's jurisdiction.

        Args:
            authority: The authority requesting reports.
            page: Page number (1-indexed).
            page_size: Number of items per page.
            status: Optional filter by report status.
            from_date: Optional filter by start date.
            to_date: Optional filter by end date.

        Returns:
            Tuple of (list of reports, total count).
        """
        # Prefer city_id FK filtering; fall back to string matching for backwards compat
        if authority.city_id:
            query = select(Report).where(Report.city_id == authority.city_id)
        else:
            query = select(Report).where(Report.location_country == authority.country)
            if authority.city:
                query = query.where(Report.location_city == authority.city)

        if status:
            query = query.where(Report.status == status)

        if from_date:
            query = query.where(Report.created_at >= from_date)

        if to_date:
            query = query.where(Report.created_at <= to_date)

        # Count total
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.order_by(Report.created_at.desc()).offset(offset).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_analytics(
        self,
        authority: Authority,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> dict:
        """Get analytics for authority's jurisdiction.

        Args:
            authority: The authority requesting analytics.
            from_date: Optional filter by start date.
            to_date: Optional filter by end date.

        Returns:
            Dictionary with analytics data.
        """
        # Prefer city_id FK filtering; fall back to string matching for backwards compat
        if authority.city_id:
            base_filter = Report.city_id == authority.city_id
        else:
            base_filter = Report.location_country == authority.country
            if authority.city:
                base_filter = and_(base_filter, Report.location_city == authority.city)

        if from_date and to_date:
            base_filter = and_(
                base_filter,
                Report.created_at >= from_date,
                Report.created_at <= to_date,
            )

        # Total reports
        total_result = await self.db.execute(
            select(func.count()).select_from(Report).where(base_filter)
        )
        total_reports = total_result.scalar() or 0

        # By status
        status_result = await self.db.execute(
            select(Report.status, func.count())
            .where(base_filter)
            .group_by(Report.status)
        )
        by_status = {row[0].value: row[1] for row in status_result}

        # By infraction (top 10)
        infraction_result = await self.db.execute(
            select(Report.infraction_id, func.count())
            .where(base_filter)
            .group_by(Report.infraction_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_infractions = [
            {"infraction_id": str(row[0]), "count": row[1]} for row in infraction_result
        ]

        # By day (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        daily_result = await self.db.execute(
            select(
                func.date_trunc("day", Report.created_at).label("date"), func.count()
            )
            .where(and_(base_filter, Report.created_at >= thirty_days_ago))
            .group_by("date")
            .order_by("date")
        )
        daily_counts = [
            {"date": row[0].isoformat(), "count": row[1]} for row in daily_result
        ]

        return {
            "total_reports": total_reports,
            "by_status": by_status,
            "top_infractions": top_infractions,
            "daily_counts": daily_counts,
        }

    async def get_heatmap_data(
        self,
        authority: Authority,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[dict]:
        """Get coordinates for heatmap visualization.

        Args:
            authority: The authority requesting heatmap data.
            from_date: Optional filter by start date.
            to_date: Optional filter by end date.

        Returns:
            List of coordinate dictionaries with lat, lng, and status.
        """
        # Prefer city_id FK filtering; fall back to string matching for backwards compat
        if authority.city_id:
            base_filter = Report.city_id == authority.city_id
        else:
            base_filter = Report.location_country == authority.country
            if authority.city:
                base_filter = and_(base_filter, Report.location_city == authority.city)

        if from_date and to_date:
            base_filter = and_(
                base_filter,
                Report.created_at >= from_date,
                Report.created_at <= to_date,
            )

        result = await self.db.execute(
            select(Report.latitude, Report.longitude, Report.status)
            .where(base_filter)
            .limit(10000)  # Limit for performance
        )

        return [
            {"lat": row[0], "lng": row[1], "status": row[2].value} for row in result
        ]
