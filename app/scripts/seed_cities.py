"""Seed script for Colombian cities.

Run with:
    python -m app.scripts.seed_cities
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.city import City

# Major Colombian cities with center coordinates and departments
COLOMBIAN_CITIES = [
    {
        "name": "Bogotá",
        "country_code": "CO",
        "state_province": "Cundinamarca",
        "latitude": 4.6097,
        "longitude": -74.0817,
        "timezone": "America/Bogota",
    },
    {
        "name": "Medellín",
        "country_code": "CO",
        "state_province": "Antioquia",
        "latitude": 6.2442,
        "longitude": -75.5812,
        "timezone": "America/Bogota",
    },
    {
        "name": "Cali",
        "country_code": "CO",
        "state_province": "Valle del Cauca",
        "latitude": 3.4516,
        "longitude": -76.5320,
        "timezone": "America/Bogota",
    },
    {
        "name": "Barranquilla",
        "country_code": "CO",
        "state_province": "Atlántico",
        "latitude": 10.9685,
        "longitude": -74.7813,
        "timezone": "America/Bogota",
    },
    {
        "name": "Cartagena",
        "country_code": "CO",
        "state_province": "Bolívar",
        "latitude": 10.3910,
        "longitude": -75.5144,
        "timezone": "America/Bogota",
    },
    {
        "name": "Bucaramanga",
        "country_code": "CO",
        "state_province": "Santander",
        "latitude": 7.1254,
        "longitude": -73.1198,
        "timezone": "America/Bogota",
    },
    {
        "name": "Cúcuta",
        "country_code": "CO",
        "state_province": "Norte de Santander",
        "latitude": 7.8939,
        "longitude": -72.5078,
        "timezone": "America/Bogota",
    },
    {
        "name": "Pereira",
        "country_code": "CO",
        "state_province": "Risaralda",
        "latitude": 4.8133,
        "longitude": -75.6961,
        "timezone": "America/Bogota",
    },
    {
        "name": "Santa Marta",
        "country_code": "CO",
        "state_province": "Magdalena",
        "latitude": 11.2408,
        "longitude": -74.1990,
        "timezone": "America/Bogota",
    },
    {
        "name": "Manizales",
        "country_code": "CO",
        "state_province": "Caldas",
        "latitude": 5.0689,
        "longitude": -75.5174,
        "timezone": "America/Bogota",
    },
]


async def seed_cities(db: AsyncSession) -> list[City]:
    """Seed Colombian cities into the database.

    Skips cities that already exist (matched by name + country_code).

    Args:
        db: Async database session.

    Returns:
        List of City objects that were created.
    """
    created = []
    for city_data in COLOMBIAN_CITIES:
        result = await db.execute(
            select(City).where(
                City.name == city_data["name"],
                City.country_code == city_data["country_code"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            continue

        city = City(**city_data)
        db.add(city)
        created.append(city)

    if created:
        await db.commit()
        for city in created:
            await db.refresh(city)

    return created


async def main() -> None:
    """Entry point for the seed script."""
    async with async_session_factory() as db:
        cities = await seed_cities(db)
        if cities:
            print(f"Seeded {len(cities)} cities:")
            for city in cities:
                print(f"  - {city.name} ({city.state_province})")
        else:
            print("All cities already exist, nothing to seed.")


if __name__ == "__main__":
    asyncio.run(main())
