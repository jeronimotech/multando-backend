"""Infraction endpoints for the Multando API.

This module provides endpoints for retrieving traffic infraction types.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.schemas.infraction import (
    InfractionCategory,
    InfractionList,
    InfractionResponse,
    InfractionSeverity,
)
from app.services.infraction import InfractionService

router = APIRouter(prefix="/infractions", tags=["infractions"])


def _build_infraction_response(infraction) -> InfractionResponse:
    """Build an InfractionResponse from an infraction model."""
    return InfractionResponse(
        id=infraction.id,
        code=infraction.code,
        name_en=infraction.name_en,
        name_es=infraction.name_es,
        description_en=infraction.description_en or "",
        description_es=infraction.description_es or "",
        category=InfractionCategory(infraction.category.value),
        severity=InfractionSeverity(infraction.severity.value),
        points_reward=infraction.points_reward,
        multa_reward=infraction.multa_reward,
        icon=infraction.icon,
    )


@router.get(
    "",
    response_model=InfractionList,
    summary="List all infractions",
    description="Get a list of all available traffic infraction types.",
)
async def list_infractions(
    db: DbSession,
) -> InfractionList:
    """List all traffic infractions.

    This is a public endpoint that returns all active infraction types
    that can be used when submitting a report.

    Args:
        db: Database session.

    Returns:
        A list of all active infractions.
    """
    infraction_service = InfractionService(db)
    infractions = await infraction_service.list_all()

    return InfractionList(
        items=[_build_infraction_response(i) for i in infractions]
    )


@router.get(
    "/{infraction_id}",
    response_model=InfractionResponse,
    summary="Get infraction by ID",
    description="Get detailed information about a specific infraction type.",
)
async def get_infraction(
    infraction_id: int,
    db: DbSession,
) -> InfractionResponse:
    """Get an infraction by ID.

    This is a public endpoint that returns details for a specific
    infraction type.

    Args:
        infraction_id: The ID of the infraction.
        db: Database session.

    Returns:
        The infraction details.

    Raises:
        HTTPException: 404 if infraction is not found.
    """
    infraction_service = InfractionService(db)
    infraction = await infraction_service.get_by_id(infraction_id)

    if not infraction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Infraction not found",
        )

    return _build_infraction_response(infraction)
