"""Verification service for managing report verification workflow."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    ActivityType,
    Badge,
    Level,
    Report,
    ReportStatus,
    User,
    UserBadge,
)


# Point rewards for verification actions
VERIFIER_POINTS = 5
VERIFIER_MULTA = Decimal("3.000000")
REPORTER_POINTS_ON_VERIFY = 15
REPORTER_MULTA_ON_VERIFY = Decimal("10.000000")
REJECTION_POINTS = 2
REJECTION_MULTA = Decimal("1.000000")


class VerificationService:
    """Service for handling report verification operations.

    This service provides methods for verifying and rejecting reports,
    awarding points to users, and checking for level-ups and badges.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the verification service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def verify_report(
        self,
        report_id: UUID,
        verifier_id: UUID,
    ) -> Report:
        """Verify a report.

        Steps:
        1. Check report exists and is pending
        2. Check verifier is not the reporter
        3. Update report status to 'verified'
        4. Set verifier_id and verified_at
        5. Award points to verifier (5 points, 3 MULTA)
        6. Award points to reporter (15 points, 10 MULTA)
        7. Create Activity records for both users
        8. Update both users' points
        9. Check if either user leveled up
        10. Check if either user earned a badge

        Args:
            report_id: The UUID of the report to verify.
            verifier_id: The UUID of the user verifying the report.

        Returns:
            The verified Report object.

        Raises:
            ValueError: If report not found, not pending, or verifier is reporter.
        """
        # Get the report with relationships
        report = await self._get_report(report_id)
        if not report:
            raise ValueError("Report not found")

        if report.status != ReportStatus.PENDING:
            raise ValueError("Only pending reports can be verified")

        if report.reporter_id == verifier_id:
            raise ValueError("You cannot verify your own report")

        # Update report status
        report.status = ReportStatus.VERIFIED
        report.verifier_id = verifier_id
        report.verified_at = datetime.now(timezone.utc)

        await self.db.flush()

        # Award points to verifier
        await self._award_points(
            user_id=verifier_id,
            points=VERIFIER_POINTS,
            multa=VERIFIER_MULTA,
            activity_type=ActivityType.VERIFICATION_DONE,
            reference_type="report",
            reference_id=report_id,
        )

        # Award points to reporter
        await self._award_points(
            user_id=report.reporter_id,
            points=REPORTER_POINTS_ON_VERIFY,
            multa=REPORTER_MULTA_ON_VERIFY,
            activity_type=ActivityType.REPORT_VERIFIED,
            reference_type="report",
            reference_id=report_id,
        )

        # Check for level ups and badges for both users
        verifier = await self._get_user(verifier_id)
        reporter = await self._get_user(report.reporter_id)

        if verifier:
            await self._check_level_up(verifier)
            await self._check_badges(verifier)

        if reporter:
            await self._check_level_up(reporter)
            await self._check_badges(reporter)

        await self.db.flush()

        # Trigger webhooks for verified report
        await self._trigger_report_webhooks(report, "report.verified")

        # Return updated report with relationships
        return await self._get_report(report_id)

    async def reject_report(
        self,
        report_id: UUID,
        verifier_id: UUID,
        reason: str,
    ) -> Report:
        """Reject a report.

        Steps:
        1. Check report exists and is pending
        2. Check verifier is not the reporter
        3. Update status to 'rejected'
        4. Set rejection_reason
        5. Award small points to verifier (2 points, 1 MULTA) for participation
        6. Create Activity record

        Args:
            report_id: The UUID of the report to reject.
            verifier_id: The UUID of the user rejecting the report.
            reason: The reason for rejection.

        Returns:
            The rejected Report object.

        Raises:
            ValueError: If report not found, not pending, or verifier is reporter.
        """
        if not reason or not reason.strip():
            raise ValueError("Rejection reason is required")

        # Get the report with relationships
        report = await self._get_report(report_id)
        if not report:
            raise ValueError("Report not found")

        if report.status != ReportStatus.PENDING:
            raise ValueError("Only pending reports can be rejected")

        if report.reporter_id == verifier_id:
            raise ValueError("You cannot reject your own report")

        # Update report status
        report.status = ReportStatus.REJECTED
        report.verifier_id = verifier_id
        report.verified_at = datetime.now(timezone.utc)
        report.rejection_reason = reason.strip()

        await self.db.flush()

        # Award participation points to verifier
        await self._award_points(
            user_id=verifier_id,
            points=REJECTION_POINTS,
            multa=REJECTION_MULTA,
            activity_type=ActivityType.VERIFICATION_DONE,
            reference_type="report",
            reference_id=report_id,
            metadata={"action": "rejected", "reason": reason.strip()},
        )

        # Check for level ups and badges for verifier
        verifier = await self._get_user(verifier_id)
        if verifier:
            await self._check_level_up(verifier)
            await self._check_badges(verifier)

        await self.db.flush()

        # Trigger webhooks for rejected report
        await self._trigger_report_webhooks(report, "report.rejected")

        # Return updated report with relationships
        return await self._get_report(report_id)

    async def _trigger_report_webhooks(
        self, report: Report, event_type: str
    ) -> None:
        """Fire webhook notifications for a report event.

        Uses Celery tasks for async delivery when a city_id is available.
        Falls back to direct delivery if Celery is unavailable.
        """
        if not report.city_id:
            return

        payload = {
            "report_id": str(report.id),
            "short_id": report.short_id,
            "status": report.status.value,
            "city_id": report.city_id,
        }

        try:
            from app.services.webhook import WebhookService

            webhook_svc = WebhookService(self.db)
            await webhook_svc.trigger_webhooks(
                city_id=report.city_id,
                event_type=event_type,
                payload=payload,
            )
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to trigger webhooks for report %s event %s",
                report.id,
                event_type,
                exc_info=True,
            )

    async def _get_report(self, report_id: UUID) -> Report | None:
        """Get a report by ID with all relationships loaded.

        Args:
            report_id: The UUID of the report.

        Returns:
            The Report object if found, None otherwise.
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

    async def _get_user(self, user_id: UUID) -> User | None:
        """Get a user by ID with relationships loaded.

        Args:
            user_id: The UUID of the user.

        Returns:
            The User object if found, None otherwise.
        """
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.level),
                selectinload(User.badges).selectinload(UserBadge.badge),
            )
            .where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def _award_points(
        self,
        user_id: UUID,
        points: int,
        multa: Decimal,
        activity_type: ActivityType,
        reference_type: str,
        reference_id: UUID,
        metadata: dict | None = None,
    ) -> Activity:
        """Create activity and update user points.

        Args:
            user_id: The UUID of the user to award points to.
            points: Number of points to award.
            multa: Amount of MULTA tokens to award.
            activity_type: The type of activity.
            reference_type: The type of referenced entity.
            reference_id: The ID of the referenced entity.
            metadata: Optional additional metadata.

        Returns:
            The created Activity object.
        """
        # Create activity record
        activity = Activity(
            user_id=user_id,
            type=activity_type,
            points_earned=points,
            multa_earned=multa,
            reference_type=reference_type,
            reference_id=str(reference_id),
            activity_metadata=metadata,
        )
        self.db.add(activity)
        await self.db.flush()

        # Update user points
        user = await self._get_user(user_id)
        if user:
            user.points += points
            await self.db.flush()

        return activity

    async def _check_level_up(self, user: User) -> Level | None:
        """Check if user should level up, return new level if so.

        Args:
            user: The user to check.

        Returns:
            The new Level if user leveled up, None otherwise.
        """
        # Get all levels ordered by min_points descending
        result = await self.db.execute(
            select(Level).order_by(Level.min_points.desc())
        )
        levels = list(result.scalars().all())

        # Find the appropriate level for user's points
        new_level = None
        for level in levels:
            if user.points >= level.min_points:
                new_level = level
                break

        if new_level and (not user.level_id or user.level_id != new_level.id):
            old_level_id = user.level_id
            user.level_id = new_level.id
            await self.db.flush()

            # Create level up activity if actually leveled up (not just setting initial level)
            if old_level_id is not None:
                level_up_activity = Activity(
                    user_id=user.id,
                    type=ActivityType.LEVEL_UP,
                    points_earned=0,
                    multa_earned=new_level.multa_bonus,
                    reference_type="level",
                    reference_id=str(new_level.id),
                    activity_metadata={
                        "new_tier": new_level.tier,
                        "title_en": new_level.title_en,
                        "title_es": new_level.title_es,
                    },
                )
                self.db.add(level_up_activity)
                await self.db.flush()

            return new_level

        return None

    async def _check_badges(self, user: User) -> list[Badge]:
        """Check if user earned any new badges.

        Args:
            user: The user to check.

        Returns:
            List of newly earned Badge objects.
        """
        # Import here to avoid circular dependency
        from app.services.gamification import GamificationService

        gamification_service = GamificationService(self.db)
        user_badges = await gamification_service.check_and_award_badges(user.id)

        return [ub.badge for ub in user_badges]
