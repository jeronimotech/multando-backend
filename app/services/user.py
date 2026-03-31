"""User service for profile management and user-related operations."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Activity,
    Report,
    ReportStatus,
    User,
    UserBadge,
)
from app.schemas.user import UserUpdate


class UserService:
    """Service for handling user profile operations.

    This service provides methods for retrieving and updating user profiles,
    managing user activities, badges, reports, and statistics.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the user service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Get a user by their ID with level and badges eagerly loaded.

        Args:
            user_id: The UUID of the user to find.

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

    async def get_by_username(self, username: str) -> User | None:
        """Get a user by their username.

        Args:
            username: The username to search for.

        Returns:
            The User object if found, None otherwise.
        """
        result = await self.db.execute(
            select(User)
            .options(
                selectinload(User.level),
                selectinload(User.badges).selectinload(UserBadge.badge),
            )
            .where(User.username == username.lower())
        )
        return result.scalar_one_or_none()

    async def update(self, user_id: UUID, data: UserUpdate) -> User:
        """Update a user's profile with only the provided fields.

        Args:
            user_id: The UUID of the user to update.
            data: The update data containing only fields to be updated.

        Returns:
            The updated User object.

        Raises:
            ValueError: If user not found or validation fails.
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        # Get the fields to update (only non-None values, excluding email)
        update_data = data.model_dump(exclude_unset=True, exclude={"email"})

        # Check username uniqueness if updating
        if "username" in update_data and update_data["username"]:
            existing = await self.get_by_username(update_data["username"])
            if existing and existing.id != user_id:
                raise ValueError("Username is already taken")

        # Apply updates
        for field, value in update_data.items():
            setattr(user, field, value)

        await self.db.flush()
        await self.db.refresh(user)

        # Reload with relationships
        return await self.get_by_id(user_id)

    async def get_user_activities(
        self, user_id: UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[Activity], int]:
        """Get paginated activities for a user.

        Args:
            user_id: The UUID of the user.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            A tuple containing the list of activities and total count.
        """
        # Get total count
        count_result = await self.db.execute(
            select(func.count(Activity.id)).where(Activity.user_id == user_id)
        )
        total = count_result.scalar_one()

        # Get paginated activities
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Activity)
            .where(Activity.user_id == user_id)
            .order_by(Activity.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        activities = list(result.scalars().all())

        return activities, total

    async def get_user_badges(self, user_id: UUID) -> list[UserBadge]:
        """Get all badges earned by a user with badge details.

        Args:
            user_id: The UUID of the user.

        Returns:
            List of UserBadge objects with badge details loaded.
        """
        result = await self.db.execute(
            select(UserBadge)
            .options(selectinload(UserBadge.badge))
            .where(UserBadge.user_id == user_id)
            .order_by(UserBadge.awarded_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_reports(
        self, user_id: UUID, page: int = 1, page_size: int = 20
    ) -> tuple[list[Report], int]:
        """Get paginated reports submitted by a user.

        Args:
            user_id: The UUID of the user.
            page: Page number (1-indexed).
            page_size: Number of items per page.

        Returns:
            A tuple containing the list of reports and total count.
        """
        # Get total count
        count_result = await self.db.execute(
            select(func.count(Report.id)).where(Report.reporter_id == user_id)
        )
        total = count_result.scalar_one()

        # Get paginated reports
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Report)
            .options(
                selectinload(Report.infraction),
                selectinload(Report.vehicle_type),
                selectinload(Report.evidences),
            )
            .where(Report.reporter_id == user_id)
            .order_by(Report.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        reports = list(result.scalars().all())

        return reports, total

    async def get_user_stats(self, user_id: UUID) -> dict:
        """Get statistics for a user.

        Args:
            user_id: The UUID of the user.

        Returns:
            A dictionary containing user statistics:
            - total_reports: Total number of reports submitted
            - verified_reports: Number of verified reports
            - rejected_reports: Number of rejected reports
            - pending_reports: Number of pending reports
            - verifications_done: Number of verifications performed by the user
            - current_streak: Current daily login streak
            - best_streak: Best daily login streak
            - verification_accuracy: Verification accuracy percentage
        """
        # Get report counts by status
        report_stats = await self.db.execute(
            select(
                Report.status,
                func.count(Report.id).label("count"),
            )
            .where(Report.reporter_id == user_id)
            .group_by(Report.status)
        )
        report_counts = {row.status: row.count for row in report_stats}

        total_reports = sum(report_counts.values())
        verified_reports = report_counts.get(ReportStatus.VERIFIED, 0)
        rejected_reports = report_counts.get(ReportStatus.REJECTED, 0)
        pending_reports = report_counts.get(ReportStatus.PENDING, 0)

        # Get verifications done count (reports verified by this user)
        verifications_result = await self.db.execute(
            select(func.count(Report.id)).where(Report.verifier_id == user_id)
        )
        verifications_done = verifications_result.scalar_one()

        # Calculate streaks from daily login activities
        current_streak, best_streak = await self._calculate_streaks(user_id)

        # Calculate verification accuracy
        total_verified_and_rejected = verified_reports + rejected_reports
        verification_accuracy = (
            (verified_reports / total_verified_and_rejected * 100)
            if total_verified_and_rejected > 0
            else 0.0
        )

        return {
            "total_reports": total_reports,
            "verified_reports": verified_reports,
            "rejected_reports": rejected_reports,
            "pending_reports": pending_reports,
            "verifications_done": verifications_done,
            "current_streak": current_streak,
            "best_streak": best_streak,
            "verification_accuracy": round(verification_accuracy, 2),
        }

    async def _calculate_streaks(self, user_id: UUID) -> tuple[int, int]:
        """Calculate current and best daily login streaks.

        Args:
            user_id: The UUID of the user.

        Returns:
            A tuple of (current_streak, best_streak).
        """
        # Get daily login activities ordered by date
        from app.models import ActivityType as ModelActivityType

        result = await self.db.execute(
            select(Activity.created_at)
            .where(
                Activity.user_id == user_id,
                Activity.type == ModelActivityType.DAILY_LOGIN,
            )
            .order_by(Activity.created_at.desc())
        )
        login_dates = [row[0].date() for row in result.fetchall()]

        if not login_dates:
            return 0, 0

        # Remove duplicates and sort descending
        unique_dates = sorted(set(login_dates), reverse=True)

        # Calculate current streak
        current_streak = 0
        today = datetime.now(timezone.utc).date()

        for i, login_date in enumerate(unique_dates):
            expected_date = today - timedelta(days=i)
            if login_date == expected_date:
                current_streak += 1
            elif login_date == expected_date - timedelta(days=1) and i == 0:
                # Allow for yesterday if no login today yet
                current_streak += 1
            else:
                break

        # Calculate best streak
        best_streak = 0
        if unique_dates:
            streak = 1
            sorted_dates = sorted(unique_dates)
            for i in range(1, len(sorted_dates)):
                if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
                    streak += 1
                else:
                    best_streak = max(best_streak, streak)
                    streak = 1
            best_streak = max(best_streak, streak)

        return current_streak, best_streak

    async def get_leaderboard(
        self,
        period: str = "all_time",
        limit: int = 10,
    ) -> tuple[list[User], int]:
        """Get the leaderboard for a specific time period.

        Args:
            period: Time period (daily, weekly, monthly, all_time).
            limit: Maximum number of entries to return.

        Returns:
            A tuple containing the list of users and total participants count.
        """
        # Calculate date range based on period
        now = datetime.now(timezone.utc)
        if period == "daily":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "weekly":
            start_date = now - timedelta(days=now.weekday())
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "monthly":
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:  # all_time
            start_date = None

        # Build query for leaderboard
        if start_date:
            # Get points earned in the period from activities
            points_subquery = (
                select(
                    Activity.user_id,
                    func.sum(Activity.points_earned).label("period_points"),
                )
                .where(Activity.created_at >= start_date)
                .group_by(Activity.user_id)
                .subquery()
            )

            # Join with users and order by period points
            result = await self.db.execute(
                select(User)
                .join(points_subquery, User.id == points_subquery.c.user_id)
                .options(
                    selectinload(User.level),
                    selectinload(User.badges).selectinload(UserBadge.badge),
                )
                .where(User.is_active == True)  # noqa: E712
                .order_by(points_subquery.c.period_points.desc())
                .limit(limit)
            )
        else:
            # All-time: use user's total points
            result = await self.db.execute(
                select(User)
                .options(
                    selectinload(User.level),
                    selectinload(User.badges).selectinload(UserBadge.badge),
                )
                .where(User.is_active == True)  # noqa: E712
                .order_by(User.points.desc())
                .limit(limit)
            )

        users = list(result.scalars().all())

        # Get total participants count
        count_result = await self.db.execute(
            select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
        )
        total_participants = count_result.scalar_one()

        return users, total_participants
