"""Gamification schemas for the Multando API.

This module contains schemas for leaderboards, stats, and gamification features.
"""

from enum import Enum

from pydantic import Field

from app.schemas.base import BaseSchema
from app.schemas.level import LevelResponse
from app.schemas.user import UserPublic


class LeaderboardPeriod(str, Enum):
    """Leaderboard time period options."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ALL_TIME = "all_time"


class LeaderboardEntry(BaseSchema):
    """Schema for a single leaderboard entry."""

    rank: int = Field(ge=1, description="User's rank on the leaderboard")
    user: UserPublic = Field(description="User information")
    points: int = Field(ge=0, description="Total points for the period")
    level: LevelResponse | None = Field(default=None, description="User's current level")


class LeaderboardResponse(BaseSchema):
    """Schema for leaderboard response."""

    entries: list[LeaderboardEntry] = Field(description="List of leaderboard entries")
    period: LeaderboardPeriod = Field(description="Time period for the leaderboard")
    total_participants: int = Field(
        default=0, description="Total number of participants"
    )


class UserStatsResponse(BaseSchema):
    """Schema for user statistics response."""

    total_reports: int = Field(default=0, ge=0, description="Total reports submitted")
    verified_reports: int = Field(
        default=0, ge=0, description="Number of verified reports"
    )
    rejected_reports: int = Field(
        default=0, ge=0, description="Number of rejected reports"
    )
    pending_reports: int = Field(
        default=0, ge=0, description="Number of pending reports"
    )
    verifications_done: int = Field(
        default=0, ge=0, description="Number of verifications performed"
    )
    current_streak: int = Field(
        default=0, ge=0, description="Current daily login streak"
    )
    best_streak: int = Field(default=0, ge=0, description="Best daily login streak")
    verification_accuracy: float = Field(
        default=0.0, ge=0, le=100, description="Verification accuracy percentage"
    )


class AchievementProgress(BaseSchema):
    """Schema for tracking progress towards an achievement."""

    badge_code: str = Field(description="Badge code for the achievement")
    name_en: str = Field(description="Achievement name in English")
    name_es: str = Field(description="Achievement name in Spanish")
    description_en: str = Field(description="Achievement description in English")
    description_es: str = Field(description="Achievement description in Spanish")
    current_progress: int = Field(ge=0, description="Current progress value")
    target_progress: int = Field(ge=1, description="Target progress to unlock")
    progress_percentage: float = Field(
        ge=0, le=100, description="Progress percentage (0-100)"
    )
    is_completed: bool = Field(description="Whether achievement is completed")


class UserAchievementsResponse(BaseSchema):
    """Schema for user achievements response."""

    completed: list[AchievementProgress] = Field(
        default_factory=list, description="Completed achievements"
    )
    in_progress: list[AchievementProgress] = Field(
        default_factory=list, description="Achievements in progress"
    )
    total_achievements: int = Field(
        default=0, description="Total number of achievements"
    )
    completed_count: int = Field(
        default=0, description="Number of completed achievements"
    )
