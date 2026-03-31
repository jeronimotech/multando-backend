"""Vehicle type endpoints for the Multando API.

This module provides endpoints for retrieving vehicle type reference data.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.schemas.vehicle_type import VehicleTypeList, VehicleTypeResponse
from app.services.vehicle_type import VehicleTypeService

router = APIRouter(prefix="/vehicle-types", tags=["vehicle-types"])


def _build_vehicle_type_response(vehicle_type) -> VehicleTypeResponse:
    """Build a VehicleTypeResponse from a vehicle type model."""
    return VehicleTypeResponse(
        id=vehicle_type.id,
        code=vehicle_type.code,
        name_en=vehicle_type.name_en,
        name_es=vehicle_type.name_es,
        icon=vehicle_type.icon,
        plate_pattern=vehicle_type.plate_pattern,
        requires_plate=vehicle_type.requires_plate,
    )


@router.get(
    "",
    response_model=VehicleTypeList,
    summary="List all vehicle types",
    description="Get a list of all available vehicle types.",
)
async def list_vehicle_types(
    db: DbSession,
) -> VehicleTypeList:
    """List all vehicle types.

    This is a public endpoint that returns all vehicle types
    that can be used when submitting a report.

    Args:
        db: Database session.

    Returns:
        A list of all vehicle types.
    """
    vehicle_type_service = VehicleTypeService(db)
    vehicle_types = await vehicle_type_service.list_all()

    return VehicleTypeList(
        items=[_build_vehicle_type_response(vt) for vt in vehicle_types]
    )


@router.get(
    "/{vehicle_type_id}",
    response_model=VehicleTypeResponse,
    summary="Get vehicle type by ID",
    description="Get detailed information about a specific vehicle type.",
)
async def get_vehicle_type(
    vehicle_type_id: int,
    db: DbSession,
) -> VehicleTypeResponse:
    """Get a vehicle type by ID.

    This is a public endpoint that returns details for a specific
    vehicle type.

    Args:
        vehicle_type_id: The ID of the vehicle type.
        db: Database session.

    Returns:
        The vehicle type details.

    Raises:
        HTTPException: 404 if vehicle type is not found.
    """
    vehicle_type_service = VehicleTypeService(db)
    vehicle_type = await vehicle_type_service.get_by_id(vehicle_type_id)

    if not vehicle_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle type not found",
        )

    return _build_vehicle_type_response(vehicle_type)
