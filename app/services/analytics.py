"""Enterprise analytics service.

Provides advanced analytics queries for the enterprise dashboard:
platform overview, heatmap data, time-series trends, reporter stats,
and authority performance metrics.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Authority, AuthorityUser, Report, ReportStatus
from app.models.report import Infraction


class AnalyticsService:
    """Enterprise analytics queries using SQLAlchemy aggregations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_overview(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        """Aggregate platform-wide metrics with optional date range.

        Returns total reports, daily/weekly/monthly trends, approval rate,
        avg response time, top infraction types, top cities, and reporter
        activity distribution.
        """
        filters = self._date_filters(date_from, date_to)

        # Total reports
        total_q = await self.db.execute(
            select(func.count(Report.id)).where(*filters)
        )
        total_reports = int(total_q.scalar() or 0)

        # Status breakdown
        status_q = await self.db.execute(
            select(Report.status, func.count(Report.id))
            .where(*filters)
            .group_by(Report.status)
        )
        status_counts: dict[str, int] = {}
        approved = 0
        for st, cnt in status_q.all():
            key = st.value if hasattr(st, "value") else str(st)
            status_counts[key] = int(cnt or 0)
            if st in (ReportStatus.APPROVED, ReportStatus.VERIFIED):
                approved += int(cnt or 0)

        approval_rate = round(approved / total_reports, 4) if total_reports else 0.0

        # Avg response time (authority_validated_at - created_at)
        delta = Report.authority_validated_at - Report.created_at
        avg_q = await self.db.execute(
            select(func.avg(func.extract("epoch", delta))).where(
                Report.authority_validated_at.isnot(None),
                *filters,
            )
        )
        avg_seconds = avg_q.scalar()
        avg_response_hours = (
            round(float(avg_seconds) / 3600.0, 2) if avg_seconds else None
        )

        # Top infraction types
        infraction_q = await self.db.execute(
            select(Infraction.name_en, func.count(Report.id).label("c"))
            .join(Report, Report.infraction_id == Infraction.id)
            .where(*filters)
            .group_by(Infraction.name_en)
            .order_by(func.count(Report.id).desc())
            .limit(10)
        )
        top_infractions = [
            {"name": name, "count": int(c)} for name, c in infraction_q.all()
        ]

        # Top cities
        city_q = await self.db.execute(
            select(Report.location_city, func.count(Report.id).label("c"))
            .where(Report.location_city.isnot(None), *filters)
            .group_by(Report.location_city)
            .order_by(func.count(Report.id).desc())
            .limit(10)
        )
        top_cities = [
            {"city": city, "count": int(c)} for city, c in city_q.all()
        ]

        # Daily reports (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        daily_q = await self.db.execute(
            select(
                func.date_trunc("day", Report.created_at).label("d"),
                func.count(Report.id).label("c"),
            )
            .where(Report.created_at >= thirty_days_ago, *filters)
            .group_by("d")
            .order_by("d")
        )
        daily_trend = [
            {"date": d.isoformat(), "count": int(c)} for d, c in daily_q.all()
        ]

        # Reporter activity distribution (reports per user, bucketed)
        reporter_q = await self.db.execute(
            select(
                Report.reporter_id,
                func.count(Report.id).label("report_count"),
            )
            .where(*filters)
            .group_by(Report.reporter_id)
        )
        report_counts = [int(row.report_count) for row in reporter_q.all()]
        distribution = {"1": 0, "2-5": 0, "6-10": 0, "11-50": 0, "50+": 0}
        for rc in report_counts:
            if rc == 1:
                distribution["1"] += 1
            elif rc <= 5:
                distribution["2-5"] += 1
            elif rc <= 10:
                distribution["6-10"] += 1
            elif rc <= 50:
                distribution["11-50"] += 1
            else:
                distribution["50+"] += 1

        return {
            "total_reports": total_reports,
            "approval_rate": approval_rate,
            "avg_response_time_hours": avg_response_hours,
            "status_breakdown": status_counts,
            "top_infractions": top_infractions,
            "top_cities": top_cities,
            "daily_trend": daily_trend,
            "reporter_activity_distribution": distribution,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_heatmap(
        self,
        city_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict[str, Any]]:
        """Return coordinate buckets (rounded to 2 decimal places) with report counts.

        Each bucket represents approximately a 1.1km x 1.1km area.
        """
        filters = self._date_filters(date_from, date_to)
        if city_id is not None:
            filters.append(Report.city_id == city_id)

        lat_bucket = func.round(Report.latitude.cast(Float), 2)
        lon_bucket = func.round(Report.longitude.cast(Float), 2)

        q = await self.db.execute(
            select(
                lat_bucket.label("lat"),
                lon_bucket.label("lon"),
                func.count(Report.id).label("count"),
            )
            .where(*filters)
            .group_by("lat", "lon")
            .order_by(func.count(Report.id).desc())
            .limit(1000)
        )

        return [
            {"lat": float(row.lat), "lon": float(row.lon), "count": int(row.count)}
            for row in q.all()
        ]

    async def get_trends(
        self,
        group_by: str = "day",
        date_from: date | None = None,
        date_to: date | None = None,
        infraction_id: int | None = None,
        city_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Time-series data: reports per day/week/month.

        Optionally grouped by infraction type or city.
        Returns arrays suitable for charting.
        """
        filters = self._date_filters(date_from, date_to)
        if infraction_id is not None:
            filters.append(Report.infraction_id == infraction_id)
        if city_id is not None:
            filters.append(Report.city_id == city_id)

        trunc_map = {"day": "day", "week": "week", "month": "month"}
        trunc = trunc_map.get(group_by, "day")

        period = func.date_trunc(trunc, Report.created_at).label("period")
        q = await self.db.execute(
            select(period, func.count(Report.id).label("count"))
            .where(*filters)
            .group_by("period")
            .order_by("period")
        )

        return [
            {"period": row.period.isoformat(), "count": int(row.count)}
            for row in q.all()
        ]

    async def get_reporter_stats(self, limit: int = 20) -> list[dict[str, Any]]:
        """Reporter activity stats with anonymized IDs.

        Returns most active reporters, their rejection rates, and avg reports.
        Reporter IDs are hashed for privacy.
        """
        import hashlib

        q = await self.db.execute(
            select(
                Report.reporter_id,
                func.count(Report.id).label("total"),
                func.count(Report.id)
                .filter(Report.status == ReportStatus.REJECTED)
                .label("rejected"),
            )
            .group_by(Report.reporter_id)
            .order_by(func.count(Report.id).desc())
            .limit(limit)
        )

        results = []
        for row in q.all():
            # Anonymize the reporter ID
            anon_id = hashlib.sha256(str(row.reporter_id).encode()).hexdigest()[:12]
            total = int(row.total or 0)
            rejected = int(row.rejected or 0)
            rejection_rate = round(rejected / total, 4) if total else 0.0
            results.append(
                {
                    "reporter_anon_id": anon_id,
                    "total_reports": total,
                    "rejected_reports": rejected,
                    "rejection_rate": rejection_rate,
                }
            )

        return results

    async def get_authority_performance(
        self, authority_id: int
    ) -> dict[str, Any]:
        """Detailed performance metrics for a specific authority.

        Returns daily throughput, backlog size, avg time-to-decision,
        and rejection breakdown by reason.
        """
        # Get member user IDs for this authority
        members_q = await self.db.execute(
            select(AuthorityUser.user_id).where(
                AuthorityUser.authority_id == authority_id
            )
        )
        member_ids = [uid for (uid,) in members_q.all()]

        if not member_ids:
            return {
                "authority_id": authority_id,
                "total_processed": 0,
                "approved": 0,
                "rejected": 0,
                "avg_time_to_decision_hours": None,
                "backlog_size": 0,
                "daily_throughput": [],
                "rejection_reasons": [],
            }

        # Total processed
        processed_q = await self.db.execute(
            select(func.count(Report.id)).where(
                Report.authority_validator_id.in_(member_ids)
            )
        )
        total_processed = int(processed_q.scalar() or 0)

        # Approved / Rejected
        approved_q = await self.db.execute(
            select(func.count(Report.id)).where(
                Report.authority_validator_id.in_(member_ids),
                Report.status.in_(
                    [ReportStatus.APPROVED, ReportStatus.VERIFIED]
                ),
            )
        )
        approved = int(approved_q.scalar() or 0)

        rejected_q = await self.db.execute(
            select(func.count(Report.id)).where(
                Report.authority_validator_id.in_(member_ids),
                Report.status == ReportStatus.REJECTED,
            )
        )
        rejected = int(rejected_q.scalar() or 0)

        # Avg time to decision
        delta = Report.authority_validated_at - Report.created_at
        avg_q = await self.db.execute(
            select(func.avg(func.extract("epoch", delta))).where(
                Report.authority_validator_id.in_(member_ids),
                Report.authority_validated_at.isnot(None),
            )
        )
        avg_seconds = avg_q.scalar()
        avg_hours = round(float(avg_seconds) / 3600.0, 2) if avg_seconds else None

        # Backlog: reports in AUTHORITY_REVIEW status not yet processed
        backlog_q = await self.db.execute(
            select(func.count(Report.id)).where(
                Report.status == ReportStatus.AUTHORITY_REVIEW
            )
        )
        backlog = int(backlog_q.scalar() or 0)

        # Daily throughput (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        daily_q = await self.db.execute(
            select(
                func.date_trunc("day", Report.authority_validated_at).label("d"),
                func.count(Report.id).label("c"),
            )
            .where(
                Report.authority_validator_id.in_(member_ids),
                Report.authority_validated_at >= thirty_days_ago,
            )
            .group_by("d")
            .order_by("d")
        )
        daily_throughput = [
            {"date": d.isoformat(), "count": int(c)} for d, c in daily_q.all()
        ]

        # Rejection reasons breakdown
        reason_q = await self.db.execute(
            select(Report.rejection_reason, func.count(Report.id).label("c"))
            .where(
                Report.authority_validator_id.in_(member_ids),
                Report.status == ReportStatus.REJECTED,
                Report.rejection_reason.isnot(None),
            )
            .group_by(Report.rejection_reason)
            .order_by(func.count(Report.id).desc())
            .limit(10)
        )
        rejection_reasons = [
            {"reason": reason, "count": int(c)} for reason, c in reason_q.all()
        ]

        return {
            "authority_id": authority_id,
            "total_processed": total_processed,
            "approved": approved,
            "rejected": rejected,
            "avg_time_to_decision_hours": avg_hours,
            "backlog_size": backlog,
            "daily_throughput": daily_throughput,
            "rejection_reasons": rejection_reasons,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _date_filters(
        date_from: date | None, date_to: date | None
    ) -> list:
        """Build SQLAlchemy filter clauses from date range."""
        filters: list = []
        if date_from is not None:
            filters.append(
                Report.created_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if date_to is not None:
            filters.append(
                Report.created_at <= datetime.combine(date_to, datetime.max.time(), tzinfo=timezone.utc)
            )
        return filters


# Need Float import for cast in heatmap
from sqlalchemy import Float  # noqa: E402
