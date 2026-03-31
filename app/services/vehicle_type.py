"""Vehicle type service for managing vehicle type reference data."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VehicleType


class VehicleTypeService:
    """Service for handling vehicle type operations.

    This service provides methods for retrieving vehicle type reference data.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the vehicle type service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def list_all(self) -> list[VehicleType]:
        """Get all vehicle types.

        Returns:
            A list of all vehicle types sorted by sort_order.
        """
        result = await self.db.execute(
            select(VehicleType).order_by(VehicleType.sort_order, VehicleType.code)
        )
        return list(result.scalars().all())

    async def get_by_id(self, vehicle_type_id: int) -> VehicleType | None:
        """Get a vehicle type by its ID.

        Args:
            vehicle_type_id: The ID of the vehicle type.

        Returns:
            The VehicleType object if found, None otherwise.
        """
        return await self.db.get(VehicleType, vehicle_type_id)

    async def get_by_code(self, code: str) -> VehicleType | None:
        """Get a vehicle type by its code.

        Args:
            code: The unique vehicle type code.

        Returns:
            The VehicleType object if found, None otherwise.
        """
        result = await self.db.execute(
            select(VehicleType).where(VehicleType.code == code.upper())
        )
        return result.scalar_one_or_none()
