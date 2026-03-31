"""Gamification endpoints for the Multando API.

This module provides endpoints for gamification features including
daily login rewards, levels, badges, and progress tracking.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.schemas.activity import ActivityResponse, ActivityType, ReferenceType
from app.schemas.badge import BadgeRarity, BadgeResponse
from app.schemas.common import MessageResponse
from app.schemas.level import LevelList, LevelResponse
from app.services.gamification import GamificationService

router = APIRouter(prefix="/gamification", tags=["gamification"])


class DailyLoginResponse(BaseModel):
    """Response for daily login claim."""

    success: bool = Field(description="Whether the daily login was claimed")
    message: str = Field(description="Status message")
    activity: ActivityResponse | None = Field(
        default=None, description="Activity record if claimed"
    )
    already_claimed: bool = Field(
        default=False, description="True if already claimed today"
    )


class BadgeProgressResponse(BaseModel):
    """Response for badge progress."""

    badge_code: str = Field(description="Badge code identifier")
    badge_id: int = Field(description="Badge ID")
    name_en: str = Field(description="Badge name in English")
    name_es: str = Field(description="Badge name in Spanish")
    description_en: str | None = Field(default=None, description="Badge description in English")
    description_es: str | None = Field(default=None, description="Badge description in Spanish")
    icon_url: str | None = Field(default=None, description="Badge icon URL")
    rarity: str = Field(description="Badge rarity")
    multa_reward: str = Field(description="MULTA reward for earning badge")
    earned: bool = Field(description="Whether user has earned this badge")
    progress: dict[str, int] = Field(description="Current progress for each criterion")
    criteria: dict[str, int] = Field(description="Required values for each criterion")


class AllBadgeProgressResponse(BaseModel):
    """Response for all badge progress."""

    badges: list[BadgeProgressResponse] = Field(description="Progress for all badges")
    total_badges: int = Field(description="Total number of badges")
    earned_count: int = Field(description="Number of badges earned")


@router.post(
    "/daily-login",
    response_model=DailyLoginResponse,
    summary="Claim daily login reward",
    description="Claim the daily login reward (1 point, 0.5 MULTA). Can only be claimed once per day.",
)
async def claim_daily_login(
    current_user: CurrentUser,
    db: DbSession,
) -> DailyLoginResponse:
    """Claim daily login reward.

    Awards 1 point and 0.5 MULTA tokens for logging in each day.
    Can only be claimed once per 24-hour period.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        DailyLoginResponse with claim status and activity if successful.
    """
    gamification_service = GamificationService(db)

    activity = await gamification_service.record_daily_login(current_user.id)

    if activity is None:
        return DailyLoginResponse(
            success=False,
            message="Daily login already claimed today",
            activity=None,
            already_claimed=True,
        )

    return DailyLoginResponse(
        success=True,
        message="Daily login reward claimed successfully! +1 point, +0.5 MULTA",
        activity=ActivityResponse(
            id=activity.id,
            type=ActivityType.DAILY_LOGIN,
            points_earned=activity.points_earned,
            multa_earned=activity.multa_earned,
            reference_type=ReferenceType.USER if activity.reference_type == "user" else None,
            reference_id=activity.reference_id,
            metadata=activity.activity_metadata,
            created_at=activity.created_at,
        ),
        already_claimed=False,
    )


@router.get(
    "/levels",
    response_model=LevelList,
    summary="Get all levels",
    description="Get all available levels in the gamification system.",
)
async def get_all_levels(
    db: DbSession,
) -> LevelList:
    """Get all levels.

    Returns all levels ordered by tier, showing point requirements
    and benefits for each level.

    Args:
        db: Database session.

    Returns:
        LevelList containing all levels.
    """
    gamification_service = GamificationService(db)

    levels = await gamification_service.get_all_levels()

    level_responses = [
        LevelResponse(
            id=level.id,
            tier=level.tier,
            title_en=level.title_en,
            title_es=level.title_es,
            min_points=level.min_points,
            icon_url=level.icon_url,
            multa_bonus=level.multa_bonus,
        )
        for level in levels
    ]

    return LevelList(items=level_responses)


@router.get(
    "/badges",
    response_model=list[BadgeResponse],
    summary="Get all badges",
    description="Get all available badges that can be earned. Limited to 100.",
)
async def get_all_badges(
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=200, description="Maximum number of badges to return"),
    offset: int = Query(default=0, ge=0, description="Number of badges to skip"),
) -> list[BadgeResponse]:
    """Get all badges.

    Returns all badges with their descriptions, requirements,
    and MULTA rewards.

    Args:
        db: Database session.

    Returns:
        List of BadgeResponse objects.
    """
    gamification_service = GamificationService(db)

    badges = await gamification_service.get_all_badges()

    return [
        BadgeResponse(
            id=badge.id,
            code=badge.code,
            name_en=badge.name_en,
            name_es=badge.name_es,
            description_en=badge.description_en or "",
            description_es=badge.description_es or "",
            icon_url=badge.icon_url,
            rarity=BadgeRarity(badge.rarity.value)
            if hasattr(badge.rarity, "value")
            else BadgeRarity(badge.rarity),
            multa_reward=badge.multa_reward,
            is_nft=badge.is_nft,
        )
        for badge in badges
    ]


@router.get(
    "/progress",
    response_model=AllBadgeProgressResponse,
    summary="Get user badge progress",
    description="Get the authenticated user's progress towards all badges.",
)
async def get_badge_progress(
    current_user: CurrentUser,
    db: DbSession,
) -> AllBadgeProgressResponse:
    """Get user's badge progress.

    Returns detailed progress for each badge, showing current values
    and required values for each criterion.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        AllBadgeProgressResponse with progress for all badges.
    """
    gamification_service = GamificationService(db)

    progress_data = await gamification_service.get_user_progress(current_user.id)

    badge_progress_list = []
    earned_count = 0

    for badge_code, data in progress_data.items():
        if data["earned"]:
            earned_count += 1

        badge_progress_list.append(
            BadgeProgressResponse(
                badge_code=badge_code,
                badge_id=data["badge_id"],
                name_en=data["name_en"],
                name_es=data["name_es"],
                description_en=data.get("description_en"),
                description_es=data.get("description_es"),
                icon_url=data.get("icon_url"),
                rarity=data["rarity"],
                multa_reward=data["multa_reward"],
                earned=data["earned"],
                progress=data["progress"],
                criteria=data["criteria"],
            )
        )

    return AllBadgeProgressResponse(
        badges=badge_progress_list,
        total_badges=len(badge_progress_list),
        earned_count=earned_count,
    )
