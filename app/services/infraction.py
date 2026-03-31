"""Infraction service for managing traffic infraction types."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Infraction


class InfractionService:
    """Service for handling infraction operations.

    This service provides methods for retrieving traffic infraction types.
    """

    def __init__(self, db: AsyncSession):
        """Initialize the infraction service.

        Args:
            db: Async database session for database operations.
        """
        self.db = db

    async def list_all(self, active_only: bool = True) -> list[Infraction]:
        """Get all infractions.

        Args:
            active_only: If True, only return active infractions.

        Returns:
            A list of all infractions sorted by sort_order.
        """
        query = select(Infraction).order_by(Infraction.sort_order, Infraction.code)

        if active_only:
            query = query.where(Infraction.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, infraction_id: int) -> Infraction | None:
        """Get an infraction by its ID.

        Args:
            infraction_id: The ID of the infraction.

        Returns:
            The Infraction object if found, None otherwise.
        """
        return await self.db.get(Infraction, infraction_id)

    async def get_by_code(self, code: str) -> Infraction | None:
        """Get an infraction by its code.

        Args:
            code: The unique infraction code.

        Returns:
            The Infraction object if found, None otherwise.
        """
        result = await self.db.execute(
            select(Infraction).where(Infraction.code == code.upper())
        )
        return result.scalar_one_or_none()
