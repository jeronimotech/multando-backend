"""User endpoints for the Multando API.

This module provides endpoints for user profile management, activities,
badges, reports, and statistics.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.models import User
from app.schemas.activity import ActivityList, ActivityResponse
from app.schemas.badge import BadgeResponse, UserBadgeResponse
from app.schemas.gamification import (
    LeaderboardEntry,
    LeaderboardPeriod,
    LeaderboardResponse,
    UserStatsResponse,
)
from app.schemas.level import LevelResponse
from app.schemas.report import LocationSchema, ReportList, ReportSummary
from app.schemas.user import UserProfile, UserPublic, UserUpdate
from app.services.user import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _user_to_profile(user: User) -> UserProfile:
    """Convert a User model to UserProfile schema.

    Args:
        user: The User model instance.

    Returns:
        UserProfile schema instance.
    """
    level_response = None
    if user.level:
        level_response = LevelResponse(
            id=user.level.id,
            tier=user.level.tier,
            title_en=user.level.title_en,
            title_es=user.level.title_es,
            description_en=user.level.description_en,
            description_es=user.level.description_es,
            min_points=user.level.min_points,
            icon_url=user.level.icon_url,
            multa_bonus=user.level.multa_bonus,
        )

    badges_response = []
    for user_badge in user.badges:
        badge = user_badge.badge
        badges_response.append(
            UserBadgeResponse(
                badge=BadgeResponse(
                    id=badge.id,
                    code=badge.code,
                    name_en=badge.name_en,
                    name_es=badge.name_es,
                    description_en=badge.description_en or "",
                    description_es=badge.description_es or "",
                    icon_url=badge.icon_url,
                    rarity=badge.rarity.value,
                    multa_reward=badge.multa_reward,
                    is_nft=badge.is_nft,
                ),
                awarded_at=user_badge.awarded_at,
                nft_mint_address=user_badge.nft_mint_address,
            )
        )

    return UserProfile(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name or user.username or "",
        avatar_url=user.avatar_url,
        points=user.points,
        level=level_response,
        badges=badges_response,
        created_at=user.created_at,
        email=user.email or "",
        phone_number=user.phone_number,
        wallet_address=user.wallet_address,
        reputation_score=user.reputation_score,
        is_verified=user.is_verified,
        role=user.role.value,
    )


def _user_to_public(user: User) -> UserPublic:
    """Convert a User model to UserPublic schema.

    Args:
        user: The User model instance.

    Returns:
        UserPublic schema instance.
    """
    level_response = None
    if user.level:
        level_response = LevelResponse(
            id=user.level.id,
            tier=user.level.tier,
            title_en=user.level.title_en,
            title_es=user.level.title_es,
            description_en=user.level.description_en,
            description_es=user.level.description_es,
            min_points=user.level.min_points,
            icon_url=user.level.icon_url,
            multa_bonus=user.level.multa_bonus,
        )

    badges_response = []
    for user_badge in user.badges:
        badge = user_badge.badge
        badges_response.append(
            UserBadgeResponse(
                badge=BadgeResponse(
                    id=badge.id,
                    code=badge.code,
                    name_en=badge.name_en,
                    name_es=badge.name_es,
                    description_en=badge.description_en or "",
                    description_es=badge.description_es or "",
                    icon_url=badge.icon_url,
                    rarity=badge.rarity.value,
                    multa_reward=badge.multa_reward,
                    is_nft=badge.is_nft,
                ),
                awarded_at=user_badge.awarded_at,
                nft_mint_address=user_badge.nft_mint_address,
            )
        )

    return UserPublic(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name or user.username or "",
        avatar_url=user.avatar_url,
        points=user.points,
        level=level_response,
        badges=badges_response,
        created_at=user.created_at,
    )


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: CurrentUser,
    db: DbSession,
) -> UserProfile:
    """Get the current user's full profile.

    Returns the authenticated user's profile including level, badges,
    and private information like email and wallet address.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The user's full profile.
    """
    user_service = UserService(db)
    user = await user_service.get_by_id(current_user.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return _user_to_profile(user)


@router.patch("/me", response_model=UserProfile)
async def update_current_user(
    data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> UserProfile:
    """Update the current user's profile.

    Partial update - only provided fields will be updated.
    Email cannot be updated through this endpoint.

    Args:
        data: The fields to update.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated user profile.

    Raises:
        HTTPException: 400 if validation fails (e.g., username taken).
    """
    user_service = UserService(db)
    try:
        user = await user_service.update(current_user.id, data)
        await db.commit()
        return _user_to_profile(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/me/activities", response_model=ActivityList)
async def get_current_user_activities(
    current_user: CurrentUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page")
    ] = 20,
) -> ActivityList:
    """Get the current user's activities.

    Returns a paginated list of the user's activities (points earned,
    badges unlocked, etc.).

    Args:
        current_user: The authenticated user.
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        Paginated list of activities.
    """
    user_service = UserService(db)
    activities, total = await user_service.get_user_activities(
        current_user.id, page, page_size
    )

    return ActivityList(
        items=[
            ActivityResponse(
                id=activity.id,
                type=activity.type.value,
                points_earned=activity.points_earned,
                multa_earned=activity.multa_earned,
                reference_type=activity.reference_type,
                reference_id=activity.reference_id,
                metadata=activity.metadata,
                created_at=activity.created_at,
            )
            for activity in activities
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/me/badges", response_model=list[UserBadgeResponse])
async def get_current_user_badges(
    current_user: CurrentUser,
    db: DbSession,
) -> list[UserBadgeResponse]:
    """Get the current user's badges.

    Returns all badges earned by the authenticated user.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        List of user badges with badge details.
    """
    user_service = UserService(db)
    user_badges = await user_service.get_user_badges(current_user.id)

    return [
        UserBadgeResponse(
            badge=BadgeResponse(
                id=ub.badge.id,
                code=ub.badge.code,
                name_en=ub.badge.name_en,
                name_es=ub.badge.name_es,
                description_en=ub.badge.description_en or "",
                description_es=ub.badge.description_es or "",
                icon_url=ub.badge.icon_url,
                rarity=ub.badge.rarity.value,
                multa_reward=ub.badge.multa_reward,
                is_nft=ub.badge.is_nft,
            ),
            awarded_at=ub.awarded_at,
            nft_mint_address=ub.nft_mint_address,
        )
        for ub in user_badges
    ]


@router.get("/me/reports", response_model=ReportList)
async def get_current_user_reports(
    current_user: CurrentUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=100, description="Items per page")
    ] = 20,
) -> ReportList:
    """Get the current user's reports.

    Returns a paginated list of traffic violation reports submitted
    by the authenticated user.

    Args:
        current_user: The authenticated user.
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        Paginated list of reports.
    """
    user_service = UserService(db)
    reports, total = await user_service.get_user_reports(
        current_user.id, page, page_size
    )

    return ReportList(
        items=[
            ReportSummary(
                id=report.id,
                short_id=report.short_id,
                status=report.status.value,
                vehicle_plate=report.vehicle_plate,
                vehicle_type={
                    "id": report.vehicle_type.id,
                    "code": report.vehicle_type.code,
                    "name_en": report.vehicle_type.name_en,
                    "name_es": report.vehicle_type.name_es,
                    "icon": report.vehicle_type.icon,
                }
                if report.vehicle_type
                else None,
                infraction={
                    "id": report.infraction.id,
                    "code": report.infraction.code,
                    "name_en": report.infraction.name_en,
                    "name_es": report.infraction.name_es,
                    "description_en": report.infraction.description_en,
                    "description_es": report.infraction.description_es,
                    "category": report.infraction.category.value,
                    "severity": report.infraction.severity.value,
                    "points_reward": report.infraction.points_reward,
                    "multa_reward": report.infraction.multa_reward,
                    "icon": report.infraction.icon,
                },
                location=LocationSchema(
                    lat=report.latitude,
                    lon=report.longitude,
                    address=report.location_address,
                    city=report.location_city,
                    country=report.location_country,
                ),
                created_at=report.created_at,
            )
            for report in reports
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_current_user_stats(
    current_user: CurrentUser,
    db: DbSession,
) -> UserStatsResponse:
    """Get the current user's statistics.

    Returns statistics including total reports, verified reports,
    verifications done, and streak information.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        User statistics response.
    """
    user_service = UserService(db)
    stats = await user_service.get_user_stats(current_user.id)

    return UserStatsResponse(**stats)


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    db: DbSession,
    period: Annotated[
        LeaderboardPeriod,
        Query(description="Time period for the leaderboard"),
    ] = LeaderboardPeriod.ALL_TIME,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Number of entries to return")
    ] = 10,
) -> LeaderboardResponse:
    """Get the leaderboard.

    Returns the top users ranked by points for the specified time period.
    This is a public endpoint.

    Args:
        db: Database session.
        period: Time period (daily, weekly, monthly, all_time).
        limit: Maximum number of entries to return.

    Returns:
        Leaderboard response with ranked entries.
    """
    user_service = UserService(db)
    users, total_participants = await user_service.get_leaderboard(
        period=period.value,
        limit=limit,
    )

    entries = []
    for rank, user in enumerate(users, start=1):
        level_response = None
        if user.level:
            level_response = LevelResponse(
                id=user.level.id,
                tier=user.level.tier,
                title_en=user.level.title_en,
                title_es=user.level.title_es,
                description_en=user.level.description_en,
                description_es=user.level.description_es,
                min_points=user.level.min_points,
                icon_url=user.level.icon_url,
                multa_bonus=user.level.multa_bonus,
            )

        entries.append(
            LeaderboardEntry(
                rank=rank,
                user=_user_to_public(user),
                points=user.points,
                level=level_response,
            )
        )

    return LeaderboardResponse(
        entries=entries,
        period=period,
        total_participants=total_participants,
    )


@router.get("/{user_id}", response_model=UserPublic)
async def get_user_public_profile(
    user_id: UUID,
    db: DbSession,
) -> UserPublic:
    """Get a user's public profile.

    Returns limited public information about a user.
    This is a public endpoint.

    Args:
        user_id: The UUID of the user to retrieve.
        db: Database session.

    Returns:
        The user's public profile.

    Raises:
        HTTPException: 404 if user not found.
    """
    user_service = UserService(db)
    user = await user_service.get_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return _user_to_public(user)
