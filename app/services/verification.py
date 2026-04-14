"""Verification service for managing report verification workflow."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
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

logger = logging.getLogger(__name__)


# Point rewards for verification actions
VERIFIER_POINTS = 5
VERIFIER_MULTA = Decimal("3.000000")
REPORTER_POINTS_ON_VERIFY = 15
REPORTER_MULTA_ON_VERIFY = Decimal("10.000000")
REJECTION_POINTS = 2
REJECTION_MULTA = Decimal("1.000000")

# Community threshold: at least N votes and >= RATIO agreement.
COMMUNITY_VOTE_MIN = 3
COMMUNITY_VOTE_RATIO = 0.8


def _community_threshold_reached(
    verifications: int,
    rejections: int,
    *,
    approve: bool,
) -> bool:
    """Return True when the community has reached consensus.

    Args:
        verifications: Total verification votes.
        rejections: Total rejection votes.
        approve: ``True`` to test for approval consensus, ``False`` for
            rejection consensus.
    """
    total = verifications + rejections
    if total == 0:
        return False
    target = verifications if approve else rejections
    if target < COMMUNITY_VOTE_MIN:
        return False
    return (target / total) >= COMMUNITY_VOTE_RATIO


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
        """Record a community verification vote for a report.

        A single vote does not immediately move the report to a verified
        state. Instead it bumps ``verification_count`` and recomputes the
        confidence score. Once the community threshold is reached (>= 3
        votes with approval rate >= 80%), the report transitions to
        ``COMMUNITY_VERIFIED`` and a RECORD submission is dispatched.

        Authority validation for an official comparendo happens separately
        in the authority review queue and is never triggered from here.

        Args:
            report_id: The UUID of the report to verify.
            verifier_id: The UUID of the user verifying the report.

        Returns:
            The updated Report object.

        Raises:
            ValueError: If report not found, already closed, or verifier is
                the reporter.
        """
        # Get the report with relationships
        report = await self._get_report(report_id)
        if not report:
            raise ValueError("Report not found")

        # Only reports still accepting community input can be voted on.
        if report.status not in (
            ReportStatus.PENDING,
            ReportStatus.AUTHORITY_REVIEW,
        ):
            raise ValueError(
                "Only pending reports can be verified"
            )

        if report.reporter_id == verifier_id:
            raise ValueError("You cannot verify your own report")

        # Record the vote and recompute confidence.
        report.verification_count = (report.verification_count or 0) + 1
        report.verifier_id = verifier_id
        report.verified_at = datetime.now(timezone.utc)

        self._recompute_confidence(report)

        threshold_reached = _community_threshold_reached(
            verifications=report.verification_count,
            rejections=report.rejection_count or 0,
            approve=True,
        )

        record_dispatched = False
        if threshold_reached and report.status != ReportStatus.COMMUNITY_VERIFIED:
            report.status = ReportStatus.COMMUNITY_VERIFIED
            logger.info(
                "Report %s reached community verification threshold "
                "(verifications=%s rejections=%s)",
                report.id,
                report.verification_count,
                report.rejection_count,
            )
            record_dispatched = True

        await self.db.flush()

        # Dispatch RECORD submission only when the community verified
        # threshold has just been reached.
        if record_dispatched and settings.RECORD_ENABLED:
            try:
                from app.integrations.record_task import submit_to_record

                submit_to_record.delay(str(report.id))
            except Exception:
                logger.warning(
                    "Failed to dispatch RECORD submission for report %s",
                    report.id,
                    exc_info=True,
                )

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

        if report.status not in (
            ReportStatus.PENDING,
            ReportStatus.AUTHORITY_REVIEW,
        ):
            raise ValueError("Only pending reports can be rejected")

        if report.reporter_id == verifier_id:
            raise ValueError("You cannot reject your own report")

        # Record the rejection vote and recompute confidence.
        report.rejection_count = (report.rejection_count or 0) + 1
        report.verifier_id = verifier_id
        report.verified_at = datetime.now(timezone.utc)
        report.rejection_reason = reason.strip()

        self._recompute_confidence(report)

        # Community rejection consensus is a final state transition.
        if _community_threshold_reached(
            verifications=report.verification_count or 0,
            rejections=report.rejection_count,
            approve=False,
        ):
            report.status = ReportStatus.REJECTED
            logger.info(
                "Report %s reached community rejection threshold "
                "(verifications=%s rejections=%s)",
                report.id,
                report.verification_count,
                report.rejection_count,
            )

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

    def _recompute_confidence(self, report: Report) -> None:
        """Recompute the confidence score for ``report`` in place.

        Requires that ``report.evidences`` and ``report.reporter`` are
        already loaded (``_get_report`` does this via selectinload).
        """
        from app.services.confidence_scorer import ConfidenceScorer

        result = ConfidenceScorer.score(
            report=report,
            evidences=report.evidences or [],
            reporter=report.reporter,
            verification_count=report.verification_count or 0,
            rejection_count=report.rejection_count or 0,
        )
        report.confidence_score = result.score
        report.confidence_factors = result.factors

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
            async with self.db.begin_nested():
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

        MULTA payouts are capped at ``settings.MAX_MULTA_PER_USER_PER_MONTH``
        per calendar month. Anything that would exceed the cap is truncated
        to the remaining allowance (possibly zero) and annotated in the
        activity metadata so the UI can explain the freeze to the user.

        Args:
            user_id: The UUID of the user to award points to.
            points: Number of points to award (can be negative for penalties).
            multa: Amount of MULTA tokens to award.
            activity_type: The type of activity.
            reference_type: The type of referenced entity.
            reference_id: The ID of the referenced entity.
            metadata: Optional additional metadata.

        Returns:
            The created Activity object.
        """
        metadata = dict(metadata or {})

        # Monthly MULTA cap. Only applies to positive awards — penalties
        # or zero-MULTA activities skip this branch entirely.
        if multa > Decimal("0"):
            cap = Decimal(str(settings.MAX_MULTA_PER_USER_PER_MONTH))
            now = datetime.now(timezone.utc)
            month_start = datetime(
                now.year, now.month, 1, tzinfo=timezone.utc
            )

            earned_this_month_result = await self.db.execute(
                select(func.coalesce(func.sum(Activity.multa_earned), 0)).where(
                    Activity.user_id == user_id,
                    Activity.multa_earned > 0,
                    Activity.created_at >= month_start,
                )
            )
            earned_this_month = Decimal(
                str(earned_this_month_result.scalar() or 0)
            )

            remaining = cap - earned_this_month
            if remaining <= Decimal("0"):
                logger.info(
                    "User %s hit monthly MULTA cap (%s); awarding 0 MULTA "
                    "for %s",
                    user_id,
                    cap,
                    activity_type,
                )
                metadata.update(
                    {
                        "multa_cap_hit": True,
                        "multa_requested": str(multa),
                        "multa_cap": str(cap),
                    }
                )
                multa = Decimal("0.000000")
            elif multa > remaining:
                logger.info(
                    "User %s exceeding monthly MULTA cap; truncating "
                    "%s -> %s (cap=%s, earned=%s)",
                    user_id,
                    multa,
                    remaining,
                    cap,
                    earned_this_month,
                )
                metadata.update(
                    {
                        "multa_cap_hit": True,
                        "multa_requested": str(multa),
                        "multa_cap": str(cap),
                    }
                )
                multa = remaining

        # Create activity record
        activity = Activity(
            user_id=user_id,
            type=activity_type,
            points_earned=points,
            multa_earned=multa,
            reference_type=reference_type,
            reference_id=str(reference_id),
            activity_metadata=metadata or None,
        )
        self.db.add(activity)
        await self.db.flush()

        # Update user points. Guard against negative balances — reputation
        # can drop but we don't want weird UI artifacts if penalties
        # outstrip lifetime earnings.
        user = await self._get_user(user_id)
        if user:
            user.points = max(0, (user.points or 0) + points)
            await self.db.flush()

        return activity

    async def apply_authority_rejection_penalty(
        self,
        report: Report,
    ) -> None:
        """Apply the false-report penalty when an authority rejects a report.

        * Debit the reporter's points by ``FALSE_REPORT_POINT_PENALTY``.
        * Write an :class:`Activity` row with negative ``points_earned``
          and ``activity_type=FALSE_REPORT_PENALTY`` so the user can see
          the debit in their timeline.
        * Increment ``users.rejected_reports_count`` so the rejection
          rate warning flag stays accurate.
        * MULTA is intentionally *not* clawed back — the token may
          already have been paid out, and re-entrancy on blockchain
          state is outside the scope of this penalty.
        """
        penalty = int(settings.FALSE_REPORT_POINT_PENALTY)

        await self._award_points(
            user_id=report.reporter_id,
            points=-penalty,
            multa=Decimal("0.000000"),
            activity_type=ActivityType.FALSE_REPORT_PENALTY,
            reference_type="report",
            reference_id=report.id,
            metadata={
                "short_id": report.short_id,
                "reason": report.rejection_reason,
                "authority_validator_id": (
                    str(report.authority_validator_id)
                    if report.authority_validator_id
                    else None
                ),
            },
        )

        reporter = await self._get_user(report.reporter_id)
        if reporter is not None:
            reporter.rejected_reports_count = (
                reporter.rejected_reports_count or 0
            ) + 1
            await self.db.flush()

        logger.info(
            "Applied false-report penalty: report=%s reporter=%s points=-%d",
            report.id,
            report.reporter_id,
            penalty,
        )

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
