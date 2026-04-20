"""Federation service for cross-instance data sharing.

Hub-side: receives and stores anonymized reports from self-hosted instances.
Sender-side: pushes anonymized report data to the central hub.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.federation import FederatedReport, FederationInstance
from app.schemas.federation import (
    FederatedReportItem,
    FederationInstanceRegister,
    FederationInstanceResponse,
    FederationStatsResponse,
    FederationCityBreakdown,
    FederationInstanceListItem,
)

logger = logging.getLogger(__name__)


def _hash_key(api_key: str) -> str:
    """SHA-256 hash of an API key for storage."""
    return hashlib.sha256(api_key.encode()).hexdigest()


class FederationService:
    """Service handling both hub-side receiving and sender-side pushing."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -----------------------------------------------------------------------
    # Hub-side (receiving)
    # -----------------------------------------------------------------------

    async def register_instance(
        self, data: FederationInstanceRegister
    ) -> FederationInstanceResponse:
        """Register a new federation instance and return its credentials."""
        import uuid

        instance_id = str(uuid.uuid4())
        api_key = secrets.token_urlsafe(32)

        instance = FederationInstance(
            instance_id=instance_id,
            name=data.name,
            api_key_hash=_hash_key(api_key),
            city=data.city,
            country=data.country,
        )
        self.db.add(instance)
        await self.db.flush()

        return FederationInstanceResponse(
            instance_id=instance_id,
            api_key=api_key,
            name=data.name,
        )

    async def validate_instance(self, instance_id: str, api_key: str) -> bool:
        """Verify that instance_id + api_key match and instance is active."""
        result = await self.db.execute(
            select(FederationInstance).where(
                FederationInstance.instance_id == instance_id,
                FederationInstance.is_active.is_(True),
            )
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            return False
        return instance.api_key_hash == _hash_key(api_key)

    async def receive_sync(
        self, instance_id: str, items: list[FederatedReportItem]
    ) -> int:
        """Bulk insert/upsert federated reports from an instance.

        Returns the number of reports received.
        """
        now = datetime.now(timezone.utc)

        # Get instance name for denormalization
        inst_result = await self.db.execute(
            select(FederationInstance).where(
                FederationInstance.instance_id == instance_id
            )
        )
        instance = inst_result.scalar_one_or_none()
        instance_name = instance.name if instance else None

        count = 0
        for item in items:
            # Upsert: skip if already synced (same instance + short_id)
            existing = await self.db.execute(
                select(FederatedReport.id).where(
                    FederatedReport.instance_id == instance_id,
                    FederatedReport.report_short_id == item.short_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                # Update status if changed
                continue

            report = FederatedReport(
                instance_id=instance_id,
                instance_name=instance_name,
                report_short_id=item.short_id,
                infraction_code=item.infraction_code,
                infraction_name=item.infraction_name,
                vehicle_category=item.vehicle_category,
                city_name=item.city_name,
                status=item.status,
                reported_at=item.reported_at,
                latitude_approx=item.latitude_approx,
                longitude_approx=item.longitude_approx,
                synced_at=now,
            )
            self.db.add(report)
            count += 1

        await self.db.flush()

        # Update instance metadata
        if instance:
            instance.last_sync_at = now
            instance.total_reports_synced = (
                instance.total_reports_synced or 0
            ) + count
            await self.db.flush()

        return count

    async def get_federation_stats(self) -> FederationStatsResponse:
        """Aggregate stats across all federated instances."""
        # Total active instances
        inst_q = await self.db.execute(
            select(func.count(FederationInstance.id)).where(
                FederationInstance.is_active.is_(True)
            )
        )
        total_instances = int(inst_q.scalar() or 0)

        # Total federated reports
        reports_q = await self.db.execute(
            select(func.count(FederatedReport.id))
        )
        total_reports = int(reports_q.scalar() or 0)

        # By-city breakdown
        city_q = await self.db.execute(
            select(
                FederatedReport.city_name,
                func.count(FederatedReport.id).label("cnt"),
            )
            .where(FederatedReport.city_name.isnot(None))
            .group_by(FederatedReport.city_name)
            .order_by(func.count(FederatedReport.id).desc())
            .limit(20)
        )
        by_city = [
            FederationCityBreakdown(city_name=name, count=int(cnt))
            for name, cnt in city_q.all()
        ]

        return FederationStatsResponse(
            total_instances=total_instances,
            total_federated_reports=total_reports,
            by_city=by_city,
        )

    async def list_instances(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[FederationInstanceListItem], int]:
        """List registered federation instances (admin)."""
        count_q = await self.db.execute(
            select(func.count(FederationInstance.id))
        )
        total = int(count_q.scalar() or 0)

        result = await self.db.execute(
            select(FederationInstance)
            .order_by(FederationInstance.registered_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        instances = result.scalars().all()

        items = [
            FederationInstanceListItem(
                instance_id=i.instance_id,
                name=i.name,
                city=i.city,
                country=i.country,
                is_active=i.is_active,
                last_sync_at=i.last_sync_at,
                total_reports_synced=i.total_reports_synced or 0,
                registered_at=i.registered_at,
            )
            for i in instances
        ]
        return items, total

    async def deactivate_instance(self, instance_id: str) -> bool:
        """Deactivate a federation instance."""
        result = await self.db.execute(
            select(FederationInstance).where(
                FederationInstance.instance_id == instance_id
            )
        )
        instance = result.scalar_one_or_none()
        if instance is None:
            return False
        instance.is_active = False
        await self.db.flush()
        return True

    # -----------------------------------------------------------------------
    # Sender-side (self-hosted instance pushing to hub)
    # -----------------------------------------------------------------------

    @staticmethod
    async def push_to_hub(reports: list) -> None:
        """Push anonymized report data to the federation hub.

        Fire-and-forget: logs errors but never raises.
        """
        if not settings.FEDERATION_ENABLED:
            return
        if not settings.FEDERATION_HUB_URL or not settings.FEDERATION_API_KEY:
            return

        try:
            items = []
            for report in reports:
                # Round coordinates to 2 decimal places (~1km privacy)
                lat_approx = (
                    round(float(report.latitude), 2)
                    if report.latitude is not None
                    else None
                )
                lon_approx = (
                    round(float(report.longitude), 2)
                    if report.longitude is not None
                    else None
                )

                # Get infraction info if loaded
                infraction_code = None
                infraction_name = None
                if hasattr(report, "infraction") and report.infraction:
                    infraction_code = report.infraction.code
                    infraction_name = report.infraction.name

                items.append(
                    {
                        "short_id": report.short_id,
                        "infraction_code": infraction_code,
                        "infraction_name": infraction_name,
                        "vehicle_category": (
                            report.vehicle_category
                            if report.vehicle_category
                            else None
                        ),
                        "city_name": report.location_city,
                        "status": (
                            report.status.value
                            if hasattr(report.status, "value")
                            else report.status
                        ),
                        "reported_at": (
                            report.created_at.isoformat()
                            if report.created_at
                            else None
                        ),
                        "latitude_approx": lat_approx,
                        "longitude_approx": lon_approx,
                    }
                )

            if not items:
                return

            payload = {
                "instance_id": settings.FEDERATION_INSTANCE_ID,
                "items": items,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{settings.FEDERATION_HUB_URL.rstrip('/')}/api/v1/federation/sync",
                    json=payload,
                    headers={
                        "X-Federation-Key": settings.FEDERATION_API_KEY,
                    },
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Federation push failed with status %s: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
        except Exception:
            logger.warning(
                "Federation push_to_hub failed", exc_info=True
            )
