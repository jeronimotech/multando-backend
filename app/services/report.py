"""Report service for managing traffic violation reports."""

import base64
import logging
import secrets
import string
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    ActivityType,
    Evidence,
    EvidenceType,
    Infraction,
    Report,
    ReportStatus,
    VehicleType,
)
from app.models.city import City
from app.schemas.evidence import EvidenceCreate
from app.schemas.report import ReportCreate
from app.services.evidence_processor import EvidenceProcessor

logger = logging.getLogger(__name__)


def generate_short_id() -> str:
    """Generate a short ID like RPT-A1B2C3.

    Returns:
        A short, human-readable report identifier.
    """
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"RPT-{suffix}"


class ReportService:
    """Service for handling report operations.

    This service provides methods for creating, retrieving, updating,
    and deleting traffic violation reports.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the report service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def create(self, reporter_id: UUID, data: ReportCreate) -> Report:
        """Create a new traffic violation report.

        Creates a report with a unique short ID and awards points to the reporter.

        Args:
            reporter_id: The UUID of the user submitting the report.
            data: Report creation data.

        Returns:
            The newly created Report object.

        Raises:
            ValueError: If infraction or vehicle type is not found.
        """
        # Verify infraction exists
        infraction = await self.db.get(Infraction, data.infraction_id)
        if not infraction:
            raise ValueError("Infraction not found")

        # Verify vehicle type exists (if provided)
        if data.vehicle_type_id:
            vehicle_type = await self.db.get(VehicleType, data.vehicle_type_id)
            if not vehicle_type:
                raise ValueError("Vehicle type not found")

        # Generate unique short_id
        short_id = generate_short_id()
        while await self.get_by_short_id(short_id):
            short_id = generate_short_id()

        # Resolve city_id from GPS coordinates (nearest active city)
        city_id = await self._resolve_city_id(
            data.location.lat, data.location.lon
        )

        # Create the report
        report = Report(
            short_id=short_id,
            reporter_id=reporter_id,
            source=data.source.value if hasattr(data.source, "value") else data.source,
            infraction_id=data.infraction_id,
            vehicle_plate=data.vehicle_plate,
            vehicle_type_id=data.vehicle_type_id,
            vehicle_category=data.vehicle_category.value
            if hasattr(data.vehicle_category, "value")
            else data.vehicle_category,
            latitude=data.location.lat,
            longitude=data.location.lon,
            location_address=data.location.address,
            location_city=data.location.city,
            location_country=data.location.country or "DO",
            city_id=city_id,
            incident_datetime=data.incident_datetime,
            status=ReportStatus.PENDING,
        )

        self.db.add(report)
        await self.db.flush()

        # Award points to reporter (create activity)
        activity = Activity(
            user_id=reporter_id,
            type=ActivityType.REPORT_SUBMITTED,
            points_earned=infraction.points_reward,
            multa_earned=infraction.multa_reward,
            reference_type="report",
            reference_id=str(report.id),
            activity_metadata={"short_id": short_id, "infraction_code": infraction.code},
        )
        self.db.add(activity)
        await self.db.flush()

        # Trigger webhooks for report creation (in a savepoint so failures
        # don't abort the main transaction)
        if report.city_id:
            try:
                async with self.db.begin_nested():
                    from app.services.webhook import WebhookService

                    webhook_svc = WebhookService(self.db)
                    await webhook_svc.trigger_webhooks(
                        city_id=report.city_id,
                        event_type="report.created",
                        payload={
                            "report_id": str(report.id),
                            "short_id": short_id,
                            "status": "pending",
                            "city_id": report.city_id,
                        },
                    )
            except Exception:
                import logging

                logging.getLogger(__name__).warning(
                    "Failed to trigger webhooks for new report %s",
                    report.id,
                    exc_info=True,
                )

        # Process inline evidence if provided
        if data.evidence_image_base64:
            try:
                image_bytes = base64.b64decode(data.evidence_image_base64)
                processor = EvidenceProcessor(self.db)
                result = await processor.verify_and_process(
                    image_bytes=image_bytes,
                    timestamp=data.evidence_timestamp,
                    latitude=data.location.lat,
                    longitude=data.location.lon,
                    signature=data.evidence_signature,
                    device_id=data.evidence_device_id,
                    image_hash=data.evidence_image_hash,
                )

                # Upload watermarked image to storage
                from app.services.whatsapp.media import MediaService

                s3_key = f"evidence/{report.id}/{result.image_hash}.jpg"
                url = await MediaService.upload_evidence(
                    s3_key, result.processed_image, data.evidence_media_type
                )

                evidence = Evidence(
                    report_id=report.id,
                    type=EvidenceType.PHOTO,
                    url=url,
                    mime_type=data.evidence_media_type,
                    file_size=len(result.processed_image),
                    capture_verified=result.verified,
                    image_hash=result.image_hash,
                    capture_signature=data.evidence_signature,
                    capture_metadata={
                        "device_id": data.evidence_device_id,
                        "capture_method": data.evidence_capture_method,
                        "timestamp": data.evidence_timestamp,
                        "verification_reasons": result.reasons,
                    },
                )
                self.db.add(evidence)
                await self.db.flush()
            except Exception:
                logger.warning(
                    "Failed to process inline evidence for report %s",
                    report.id,
                    exc_info=True,
                )

        # Refresh and return with relationships
        await self.db.refresh(report)
        return await self.get_by_id(report.id)

    async def _resolve_city_id(self, lat: float, lon: float) -> int | None:
        """Find the nearest active city for the given coordinates.

        Uses a simple Euclidean distance approximation on lat/lon which is
        sufficient for matching to the nearest major city. A threshold of
        ~0.5 degrees (~55 km) prevents assigning distant cities.

        Args:
            lat: Latitude of the report location.
            lon: Longitude of the report location.

        Returns:
            The city ID of the nearest active city, or None if no city is close enough.
        """
        # Simple distance: order by (lat-lat)^2 + (lon-lon)^2
        distance_expr = (
            (City.latitude - lat) * (City.latitude - lat)
            + (City.longitude - lon) * (City.longitude - lon)
        )
        result = await self.db.execute(
            select(City.id, distance_expr.label("dist"))
            .where(City.is_active.is_(True))
            .order_by(distance_expr)
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None

        # Threshold: ~0.5 degrees squared = 0.25
        # At the equator 0.5 deg ~ 55 km, which is reasonable for city matching
        if row.dist > 0.25:
            return None

        return row.id

    async def get_by_id(self, report_id: UUID) -> Report | None:
        """Get a report by its UUID with all relations.

        Args:
            report_id: The UUID of the report.

        Returns:
            The Report object with relations if found, None otherwise.
        """
        result = await self.db.execute(
            select(Report)
            .options(
                selectinload(Report.reporter),
                selectinload(Report.verifier),
                selectinload(Report.infraction),
                selectinload(Report.vehicle_type),
                selectinload(Report.evidences),
            )
            .where(Report.id == report_id)
        )
        return result.scalar_one_or_none()

    async def get_by_short_id(self, short_id: str) -> Report | None:
        """Get a report by its short ID.

        Args:
            short_id: The human-readable short ID (e.g., RPT-A1B2C3).

        Returns:
            The Report object with relations if found, None otherwise.
        """
        result = await self.db.execute(
            select(Report)
            .options(
                selectinload(Report.reporter),
                selectinload(Report.verifier),
                selectinload(Report.infraction),
                selectinload(Report.vehicle_type),
                selectinload(Report.evidences),
            )
            .where(Report.short_id == short_id.upper())
        )
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        page: int = 1,
        page_size: int = 20,
        status: ReportStatus | None = None,
        infraction_id: int | None = None,
        reporter_id: UUID | None = None,
        city: str | None = None,
    ) -> tuple[list[Report], int]:
        """List reports with pagination and filtering.

        Args:
            page: Page number (1-indexed).
            page_size: Number of items per page.
            status: Filter by report status.
            infraction_id: Filter by infraction ID.
            reporter_id: Filter by reporter ID.
            city: Filter by city name.

        Returns:
            A tuple of (list of reports, total count).
        """
        # Build base query
        query = select(Report).options(
            selectinload(Report.reporter),
            selectinload(Report.verifier),
            selectinload(Report.infraction),
            selectinload(Report.vehicle_type),
            selectinload(Report.evidences),
        )

        # Apply filters
        if status:
            query = query.where(Report.status == status)
        if infraction_id:
            query = query.where(Report.infraction_id == infraction_id)
        if reporter_id:
            query = query.where(Report.reporter_id == reporter_id)
        if city:
            query = query.where(Report.location_city.ilike(f"%{city}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Report.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        reports = list(result.scalars().all())

        return reports, total

    async def get_by_plate(self, plate: str) -> list[Report]:
        """Get all reports for a vehicle plate.

        Args:
            plate: The vehicle license plate number.

        Returns:
            A list of reports for the specified plate.
        """
        normalized_plate = plate.upper().strip()
        result = await self.db.execute(
            select(Report)
            .options(
                selectinload(Report.reporter),
                selectinload(Report.verifier),
                selectinload(Report.infraction),
                selectinload(Report.vehicle_type),
                selectinload(Report.evidences),
            )
            .where(Report.vehicle_plate == normalized_plate)
            .order_by(Report.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending_for_verification(
        self, user_id: UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[Report], int]:
        """Get reports pending verification, excluding user's own reports.

        Args:
            user_id: The UUID of the current user (to exclude their reports).
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            A tuple of (list of pending reports, total count).
        """
        # Build base query
        query = (
            select(Report)
            .options(
                selectinload(Report.reporter),
                selectinload(Report.verifier),
                selectinload(Report.infraction),
                selectinload(Report.vehicle_type),
                selectinload(Report.evidences),
            )
            .where(Report.status == ReportStatus.PENDING)
            .where(Report.reporter_id != user_id)
        )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination and ordering
        query = query.order_by(Report.created_at.asc())  # Oldest first for verification
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        reports = list(result.scalars().all())

        return reports, total

    async def add_evidence(
        self,
        report_id: UUID,
        evidence_data: dict,
    ) -> Evidence:
        """Add evidence to a report.

        Args:
            report_id: The UUID of the report.
            evidence_data: Evidence data including type, url, mime_type, etc.

        Returns:
            The newly created Evidence object.

        Raises:
            ValueError: If report is not found.
        """
        report = await self.get_by_id(report_id)
        if not report:
            raise ValueError("Report not found")

        evidence = Evidence(
            report_id=report_id,
            type=evidence_data["type"],
            url=evidence_data["url"],
            thumbnail_url=evidence_data.get("thumbnail_url"),
            mime_type=evidence_data["mime_type"],
            file_size=evidence_data.get("file_size", 0),
            ipfs_hash=evidence_data.get("ipfs_hash"),
        )

        self.db.add(evidence)
        await self.db.flush()
        await self.db.refresh(evidence)

        return evidence

    async def delete(self, report_id: UUID, user_id: UUID) -> bool:
        """Delete a report.

        Only the report owner can delete, and only if the status is pending.

        Args:
            report_id: The UUID of the report to delete.
            user_id: The UUID of the user requesting deletion.

        Returns:
            True if deleted successfully.

        Raises:
            ValueError: If report not found, user is not owner, or report is not pending.
        """
        report = await self.get_by_id(report_id)
        if not report:
            raise ValueError("Report not found")

        if report.reporter_id != user_id:
            raise ValueError("Only the report owner can delete the report")

        if report.status != ReportStatus.PENDING:
            raise ValueError("Only pending reports can be deleted")

        await self.db.delete(report)
        await self.db.flush()

        return True
