"""Gamification service for managing game mechanics and rewards."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    ActivityType,
    Badge,
    EvidenceType,
    Level,
    Report,
    ReportStatus,
    User,
    UserBadge,
)


# Badge criteria definitions
BADGE_CRITERIA = {
    "newbie_reporter": {"reports_submitted": 1},
    "eagle_eye": {"reports_verified": 10},
    "road_guardian": {"reports_submitted": 50},
    "truth_seeker": {"verifications_done": 25},
    "community_champion": {"reports_submitted": 100, "verifications_done": 100},
    "influencer": {"referrals": 10},
    "photo_journalist": {"reports_with_video": 20},
}

# Daily login rewards
DAILY_LOGIN_POINTS = 1
DAILY_LOGIN_MULTA = Decimal("0.500000")

# Referral rewards
REFERRAL_POINTS = 20
REFERRAL_MULTA = Decimal("15.000000")


class GamificationService:
    """Service for handling gamification features.

    This service provides methods for recording activities, checking badges,
    managing daily logins, and tracking user progress.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the gamification service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def record_daily_login(self, user_id: UUID) -> Activity | None:
        """Record daily login.

        Steps:
        1. Check if already logged in today
        2. If not, create activity with 1 point, 0.5 MULTA
        3. Update user points
        4. Return activity or None if already logged in

        Args:
            user_id: The UUID of the user logging in.

        Returns:
            The created Activity if first login today, None if already logged in.
        """
        # Check if user already logged in today
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        result = await self.db.execute(
            select(Activity)
            .where(
                Activity.user_id == user_id,
                Activity.type == ActivityType.DAILY_LOGIN,
                Activity.created_at >= today_start,
            )
            .limit(1)
        )
        existing_login = result.scalar_one_or_none()

        if existing_login:
            return None  # Already logged in today

        # Create daily login activity
        activity = Activity(
            user_id=user_id,
            type=ActivityType.DAILY_LOGIN,
            points_earned=DAILY_LOGIN_POINTS,
            multa_earned=DAILY_LOGIN_MULTA,
            reference_type="user",
            reference_id=str(user_id),
            activity_metadata={"date": today_start.isoformat()},
        )
        self.db.add(activity)
        await self.db.flush()

        # Update user points
        user = await self._get_user(user_id)
        if user:
            user.points += DAILY_LOGIN_POINTS
            user.last_login_at = datetime.now(timezone.utc)
            await self.db.flush()

        return activity

    async def record_referral(
        self,
        referrer_id: UUID,
        referred_user_id: UUID,
    ) -> Activity:
        """Award points for successful referral.

        Awards 20 points, 15 MULTA for successful referral.

        Args:
            referrer_id: The UUID of the user who made the referral.
            referred_user_id: The UUID of the newly referred user.

        Returns:
            The created Activity object.
        """
        # Create referral activity
        activity = Activity(
            user_id=referrer_id,
            type=ActivityType.REFERRAL,
            points_earned=REFERRAL_POINTS,
            multa_earned=REFERRAL_MULTA,
            reference_type="user",
            reference_id=str(referred_user_id),
            activity_metadata={"referred_user_id": str(referred_user_id)},
        )
        self.db.add(activity)
        await self.db.flush()

        # Update referrer's points
        user = await self._get_user(referrer_id)
        if user:
            user.points += REFERRAL_POINTS
            await self.db.flush()

        return activity

    async def check_and_award_badges(self, user_id: UUID) -> list[UserBadge]:
        """Check all badge criteria and award any earned badges.

        Args:
            user_id: The UUID of the user to check.

        Returns:
            List of newly awarded UserBadge objects.
        """
        # Get user's current badges
        existing_badges_result = await self.db.execute(
            select(UserBadge.badge_id).where(UserBadge.user_id == user_id)
        )
        existing_badge_ids = set(row[0] for row in existing_badges_result.fetchall())

        # Get all badges
        badges_result = await self.db.execute(select(Badge))
        all_badges = list(badges_result.scalars().all())

        # Get user's progress
        progress = await self._get_user_badge_progress(user_id)

        awarded_badges = []

        for badge in all_badges:
            # Skip if already has this badge
            if badge.id in existing_badge_ids:
                continue

            # Check if badge has criteria we can evaluate
            badge_code = badge.code
            if badge_code not in BADGE_CRITERIA:
                # If badge has stored criteria in the database, use that
                if badge.criteria:
                    criteria = badge.criteria
                else:
                    continue
            else:
                criteria = BADGE_CRITERIA[badge_code]

            # Check if all criteria are met
            criteria_met = True
            for key, required_value in criteria.items():
                current_value = progress.get(key, 0)
                if current_value < required_value:
                    criteria_met = False
                    break

            if criteria_met:
                # Award the badge
                user_badge = UserBadge(
                    user_id=user_id,
                    badge_id=badge.id,
                    awarded_at=datetime.now(timezone.utc),
                )
                self.db.add(user_badge)
                await self.db.flush()

                # Refresh to load badge relationship
                await self.db.refresh(user_badge)
                user_badge_with_badge = await self.db.execute(
                    select(UserBadge)
                    .options(selectinload(UserBadge.badge))
                    .where(UserBadge.id == user_badge.id)
                )
                user_badge = user_badge_with_badge.scalar_one()

                awarded_badges.append(user_badge)

                # Create badge earned activity
                badge_activity = Activity(
                    user_id=user_id,
                    type=ActivityType.BADGE_EARNED,
                    points_earned=0,
                    multa_earned=badge.multa_reward,
                    reference_type="badge",
                    reference_id=str(badge.id),
                    activity_metadata={
                        "badge_code": badge.code,
                        "badge_name_en": badge.name_en,
                        "badge_name_es": badge.name_es,
                    },
                )
                self.db.add(badge_activity)
                await self.db.flush()

        return awarded_badges

    async def get_user_progress(self, user_id: UUID) -> dict:
        """Get user's progress towards all badges.

        Returns:
            {
                "badge_code": {
                    "earned": bool,
                    "progress": {"criteria_key": current_value},
                    "criteria": {"criteria_key": required_value}
                }
            }

        Args:
            user_id: The UUID of the user.

        Returns:
            Dictionary with progress for each badge.
        """
        # Get user's current badges
        existing_badges_result = await self.db.execute(
            select(UserBadge)
            .options(selectinload(UserBadge.badge))
            .where(UserBadge.user_id == user_id)
        )
        user_badges = list(existing_badges_result.scalars().all())
        earned_badge_codes = {ub.badge.code for ub in user_badges}

        # Get all badges
        badges_result = await self.db.execute(select(Badge))
        all_badges = list(badges_result.scalars().all())

        # Get user's progress values
        progress_values = await self._get_user_badge_progress(user_id)

        result = {}
        for badge in all_badges:
            badge_code = badge.code
            is_earned = badge_code in earned_badge_codes

            # Get criteria
            if badge_code in BADGE_CRITERIA:
                criteria = BADGE_CRITERIA[badge_code]
            elif badge.criteria:
                criteria = badge.criteria
            else:
                criteria = {}

            # Calculate progress for each criterion
            progress = {}
            for key, required_value in criteria.items():
                progress[key] = progress_values.get(key, 0)

            result[badge_code] = {
                "earned": is_earned,
                "progress": progress,
                "criteria": criteria,
                "badge_id": badge.id,
                "name_en": badge.name_en,
                "name_es": badge.name_es,
                "description_en": badge.description_en,
                "description_es": badge.description_es,
                "icon_url": badge.icon_url,
                "rarity": badge.rarity.value if hasattr(badge.rarity, "value") else badge.rarity,
                "multa_reward": str(badge.multa_reward),
            }

        return result

    async def get_all_levels(self) -> list[Level]:
        """Get all levels ordered by tier.

        Returns:
            List of Level objects ordered by tier.
        """
        result = await self.db.execute(
            select(Level).order_by(Level.tier.asc())
        )
        return list(result.scalars().all())

    async def get_all_badges(self) -> list[Badge]:
        """Get all badges.

        Returns:
            List of Badge objects.
        """
        result = await self.db.execute(select(Badge))
        return list(result.scalars().all())

    async def _get_user(self, user_id: UUID) -> User | None:
        """Get a user by ID.

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

    async def _get_user_badge_progress(self, user_id: UUID) -> dict:
        """Get progress values for badge criteria.

        Args:
            user_id: The UUID of the user.

        Returns:
            Dictionary with current values for all badge criteria keys.
        """
        progress = {}

        # Count reports submitted
        reports_submitted_result = await self.db.execute(
            select(func.count(Report.id)).where(Report.reporter_id == user_id)
        )
        progress["reports_submitted"] = reports_submitted_result.scalar_one() or 0

        # Count reports verified (reports where this user got verified status)
        reports_verified_result = await self.db.execute(
            select(func.count(Report.id)).where(
                Report.reporter_id == user_id,
                Report.status == ReportStatus.VERIFIED,
            )
        )
        progress["reports_verified"] = reports_verified_result.scalar_one() or 0

        # Count verifications done (reports this user verified)
        verifications_done_result = await self.db.execute(
            select(func.count(Report.id)).where(Report.verifier_id == user_id)
        )
        progress["verifications_done"] = verifications_done_result.scalar_one() or 0

        # Count referrals
        referrals_result = await self.db.execute(
            select(func.count(Activity.id)).where(
                Activity.user_id == user_id,
                Activity.type == ActivityType.REFERRAL,
            )
        )
        progress["referrals"] = referrals_result.scalar_one() or 0

        # Count reports with video evidence
        # First get all user's report IDs
        from app.models import Evidence

        reports_with_video_result = await self.db.execute(
            select(func.count(func.distinct(Report.id)))
            .join(Evidence, Evidence.report_id == Report.id)
            .where(
                Report.reporter_id == user_id,
                Evidence.type == EvidenceType.VIDEO,
            )
        )
        progress["reports_with_video"] = reports_with_video_result.scalar_one() or 0

        return progress
