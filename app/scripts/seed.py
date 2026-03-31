"""Seed database with initial data.

This script populates the database with initial data for:
- Levels (7 gamification tiers)
- Badges (7 achievement badges)
- Infractions (15 traffic violation types)
- Vehicle Types (10 vehicle categories)

The script is idempotent - it skips data that already exists.

Usage:
    python -m app.scripts.seed
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models import Badge, BadgeRarity, Infraction, InfractionCategory, InfractionSeverity, Level, VehicleType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# LEVELS DATA
# ============================================================
LEVELS_DATA: list[dict[str, Any]] = [
    {
        "tier": 1,
        "title_en": "Initiated Explorer",
        "title_es": "Explorador Iniciado",
        "description_en": "Welcome to Multando! You're just starting your journey.",
        "description_es": "Bienvenido a Multando! Acabas de comenzar tu viaje.",
        "min_points": 0,
        "multa_bonus": Decimal("0.00"),
    },
    {
        "tier": 2,
        "title_en": "Path Finder",
        "title_es": "Buscador de Caminos",
        "description_en": "You're finding your way and making a difference.",
        "description_es": "Estas encontrando tu camino y haciendo la diferencia.",
        "min_points": 50,
        "multa_bonus": Decimal("25.00"),
    },
    {
        "tier": 3,
        "title_en": "Quest Seeker",
        "title_es": "Buscador de Misiones",
        "description_en": "Always on the lookout for new challenges.",
        "description_es": "Siempre en busca de nuevos desafios.",
        "min_points": 150,
        "multa_bonus": Decimal("50.00"),
    },
    {
        "tier": 4,
        "title_en": "Knowledge Guardian",
        "title_es": "Guardian del Conocimiento",
        "description_en": "Your experience helps maintain road safety.",
        "description_es": "Tu experiencia ayuda a mantener la seguridad vial.",
        "min_points": 300,
        "multa_bonus": Decimal("75.00"),
    },
    {
        "tier": 5,
        "title_en": "Pioneer Leader",
        "title_es": "Lider Pionero",
        "description_en": "Leading by example in traffic safety reporting.",
        "description_es": "Liderando con el ejemplo en reportes de seguridad vial.",
        "min_points": 500,
        "multa_bonus": Decimal("100.00"),
    },
    {
        "tier": 6,
        "title_en": "Visionary Architect",
        "title_es": "Arquitecto Visionario",
        "description_en": "Building a safer community through your actions.",
        "description_es": "Construyendo una comunidad mas segura con tus acciones.",
        "min_points": 750,
        "multa_bonus": Decimal("150.00"),
    },
    {
        "tier": 7,
        "title_en": "Legend Crafter",
        "title_es": "Artesano de Leyenda",
        "description_en": "A legendary contributor to road safety.",
        "description_es": "Un contribuidor legendario a la seguridad vial.",
        "min_points": 1000,
        "multa_bonus": Decimal("250.00"),
    },
]


# ============================================================
# BADGES DATA
# ============================================================
BADGES_DATA: list[dict[str, Any]] = [
    {
        "code": "newbie_reporter",
        "name_en": "Newbie Reporter",
        "name_es": "Reportero Novato",
        "description_en": "Submit your first traffic violation report.",
        "description_es": "Envia tu primer reporte de infraccion de transito.",
        "rarity": BadgeRarity.COMMON,
        "multa_reward": Decimal("10.000000"),
        "criteria": {"reports_submitted": 1},
    },
    {
        "code": "eagle_eye",
        "name_en": "Eagle Eye",
        "name_es": "Ojo de Aguila",
        "description_en": "Have 10 of your reports verified by the community.",
        "description_es": "Ten 10 de tus reportes verificados por la comunidad.",
        "rarity": BadgeRarity.RARE,
        "multa_reward": Decimal("25.000000"),
        "criteria": {"reports_verified": 10},
    },
    {
        "code": "road_guardian",
        "name_en": "Road Guardian",
        "name_es": "Guardian de las Carreteras",
        "description_en": "Submit 50 traffic violation reports.",
        "description_es": "Envia 50 reportes de infracciones de transito.",
        "rarity": BadgeRarity.EPIC,
        "multa_reward": Decimal("50.000000"),
        "criteria": {"reports_submitted": 50},
    },
    {
        "code": "truth_seeker",
        "name_en": "Truth Seeker",
        "name_es": "Buscador de la Verdad",
        "description_en": "Verify 25 reports from other users.",
        "description_es": "Verifica 25 reportes de otros usuarios.",
        "rarity": BadgeRarity.RARE,
        "multa_reward": Decimal("25.000000"),
        "criteria": {"verifications_done": 25},
    },
    {
        "code": "community_champion",
        "name_en": "Community Champion",
        "name_es": "Campeon de la Comunidad",
        "description_en": "Submit 100 reports and verify 100 reports.",
        "description_es": "Envia 100 reportes y verifica 100 reportes.",
        "rarity": BadgeRarity.LEGENDARY,
        "multa_reward": Decimal("100.000000"),
        "criteria": {"reports_submitted": 100, "verifications_done": 100},
    },
    {
        "code": "influencer",
        "name_en": "Influencer",
        "name_es": "Influenciador",
        "description_en": "Refer 10 new users to Multando.",
        "description_es": "Refiere 10 nuevos usuarios a Multando.",
        "rarity": BadgeRarity.EPIC,
        "multa_reward": Decimal("50.000000"),
        "criteria": {"referrals": 10},
    },
    {
        "code": "photo_journalist",
        "name_en": "Photo Journalist",
        "name_es": "Fotoperiodista",
        "description_en": "Submit 20 reports with video evidence.",
        "description_es": "Envia 20 reportes con evidencia de video.",
        "rarity": BadgeRarity.RARE,
        "multa_reward": Decimal("25.000000"),
        "criteria": {"reports_with_video": 20},
    },
]


# ============================================================
# INFRACTIONS DATA
# ============================================================
INFRACTIONS_DATA: list[dict[str, Any]] = [
    {
        "code": "SPD001",
        "name_en": "Speeding",
        "name_es": "Exceso de velocidad",
        "description_en": "Vehicle exceeding the posted speed limit.",
        "description_es": "Vehiculo excediendo el limite de velocidad.",
        "category": InfractionCategory.SPEED,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 1,
    },
    {
        "code": "DRK001",
        "name_en": "Drunk Driving",
        "name_es": "Conducir ebrio",
        "description_en": "Driving under the influence of alcohol.",
        "description_es": "Conducir bajo la influencia del alcohol.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.CRITICAL,
        "points_reward": 20,
        "multa_reward": Decimal("15.000000"),
        "sort_order": 2,
    },
    {
        "code": "SBT001",
        "name_en": "No Seatbelt",
        "name_es": "Sin cinturon",
        "description_en": "Driver or passenger not wearing seatbelt.",
        "description_es": "Conductor o pasajero sin cinturon de seguridad.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 3,
    },
    {
        "code": "SIG001",
        "name_en": "Running Red Light",
        "name_es": "Pasarse el semaforo",
        "description_en": "Vehicle passing through red traffic light.",
        "description_es": "Vehiculo pasando semaforo en rojo.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 4,
    },
    {
        "code": "PRK001",
        "name_en": "Illegal Parking",
        "name_es": "Parqueo ilegal",
        "description_en": "Vehicle parked in prohibited zone.",
        "description_es": "Vehiculo estacionado en zona prohibida.",
        "category": InfractionCategory.PARKING,
        "severity": InfractionSeverity.LOW,
        "points_reward": 5,
        "multa_reward": Decimal("3.000000"),
        "sort_order": 5,
    },
    {
        "code": "PHN001",
        "name_en": "Phone While Driving",
        "name_es": "Celular al conducir",
        "description_en": "Using mobile phone while driving.",
        "description_es": "Usando el celular mientras conduce.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 6,
    },
    {
        "code": "HLM001",
        "name_en": "No Helmet",
        "name_es": "Sin casco",
        "description_en": "Motorcycle rider without helmet.",
        "description_es": "Motociclista sin casco.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 7,
    },
    {
        "code": "OVR001",
        "name_en": "Overcrowding",
        "name_es": "Sobrecupo",
        "description_en": "Vehicle carrying more passengers than allowed.",
        "description_es": "Vehiculo llevando mas pasajeros de lo permitido.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 8,
    },
    {
        "code": "WRG001",
        "name_en": "Wrong Way",
        "name_es": "Contravia",
        "description_en": "Driving against traffic direction.",
        "description_es": "Conduciendo en direccion contraria al trafico.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.CRITICAL,
        "points_reward": 20,
        "multa_reward": Decimal("15.000000"),
        "sort_order": 9,
    },
    {
        "code": "DBL001",
        "name_en": "Double Parking",
        "name_es": "Doble fila",
        "description_en": "Vehicle parked in double file blocking traffic.",
        "description_es": "Vehiculo estacionado en doble fila bloqueando el trafico.",
        "category": InfractionCategory.PARKING,
        "severity": InfractionSeverity.LOW,
        "points_reward": 5,
        "multa_reward": Decimal("3.000000"),
        "sort_order": 10,
    },
    {
        "code": "CHD001",
        "name_en": "No Child Seat",
        "name_es": "Sin silla de nino",
        "description_en": "Child not in proper car seat.",
        "description_es": "Nino sin silla de seguridad apropiada.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 11,
    },
    {
        "code": "MNV001",
        "name_en": "Dangerous Maneuver",
        "name_es": "Maniobra peligrosa",
        "description_en": "Performing dangerous driving maneuvers.",
        "description_es": "Realizando maniobras de conduccion peligrosas.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 12,
    },
    {
        "code": "INT001",
        "name_en": "Blocking Intersection",
        "name_es": "Bloquear interseccion",
        "description_en": "Vehicle blocking intersection during red light.",
        "description_es": "Vehiculo bloqueando interseccion durante semaforo rojo.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 13,
    },
    {
        "code": "DET001",
        "name_en": "Vehicle Deterioration",
        "name_es": "Vehiculo deteriorado",
        "description_en": "Vehicle in poor condition posing safety risk.",
        "description_es": "Vehiculo en mal estado representando riesgo de seguridad.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.LOW,
        "points_reward": 5,
        "multa_reward": Decimal("3.000000"),
        "sort_order": 14,
    },
    {
        "code": "ABU001",
        "name_en": "Abuse of Power",
        "name_es": "Abuso de autoridad",
        "description_en": "Authority figure abusing traffic powers.",
        "description_es": "Figura de autoridad abusando de poderes de transito.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 15,
    },
]


# ============================================================
# VEHICLE TYPES DATA
# ============================================================
VEHICLE_TYPES_DATA: list[dict[str, Any]] = [
    {
        "code": "CAR",
        "name_en": "Private Car",
        "name_es": "Carro particular",
        "requires_plate": True,
        "plate_pattern": "^[A-Z]{3}[0-9]{3}$",
        "sort_order": 1,
    },
    {
        "code": "MOTO",
        "name_en": "Motorcycle",
        "name_es": "Motocicleta",
        "requires_plate": True,
        "plate_pattern": "^[A-Z]{3}[0-9]{2}[A-Z]$",
        "sort_order": 2,
    },
    {
        "code": "TAXI",
        "name_en": "Taxi",
        "name_es": "Taxi",
        "requires_plate": True,
        "plate_pattern": "^[A-Z]{3}[0-9]{3}$",
        "sort_order": 3,
    },
    {
        "code": "BUS",
        "name_en": "Public Bus",
        "name_es": "Bus publico",
        "requires_plate": True,
        "plate_pattern": None,
        "sort_order": 4,
    },
    {
        "code": "TRUCK",
        "name_en": "Truck",
        "name_es": "Camion",
        "requires_plate": True,
        "plate_pattern": None,
        "sort_order": 5,
    },
    {
        "code": "VAN",
        "name_en": "Van",
        "name_es": "Van",
        "requires_plate": True,
        "plate_pattern": None,
        "sort_order": 6,
    },
    {
        "code": "BIKE",
        "name_en": "Bicycle",
        "name_es": "Bicicleta",
        "requires_plate": False,
        "plate_pattern": None,
        "sort_order": 7,
    },
    {
        "code": "SCOOTER",
        "name_en": "E-Scooter",
        "name_es": "Patineta electrica",
        "requires_plate": False,
        "plate_pattern": None,
        "sort_order": 8,
    },
    {
        "code": "PEDESTRIAN",
        "name_en": "Pedestrian",
        "name_es": "Peaton",
        "requires_plate": False,
        "plate_pattern": None,
        "sort_order": 9,
    },
    {
        "code": "DIPLOMATIC",
        "name_en": "Diplomatic",
        "name_es": "Diplomatico",
        "requires_plate": True,
        "plate_pattern": "^[A-Z]{2}[0-9]{4}$",
        "sort_order": 10,
    },
]


async def seed_levels(session: AsyncSession) -> int:
    """Seed levels table with gamification tiers.

    Args:
        session: Async database session.

    Returns:
        Number of levels created.
    """
    created = 0

    for level_data in LEVELS_DATA:
        # Check if level already exists by tier
        result = await session.execute(
            select(Level).where(Level.tier == level_data["tier"])
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            level = Level(**level_data)
            session.add(level)
            created += 1
            logger.info(f"Created level: Tier {level_data['tier']} - {level_data['title_en']}")
        else:
            logger.debug(f"Level already exists: Tier {level_data['tier']}")

    return created


async def seed_badges(session: AsyncSession) -> int:
    """Seed badges table with achievement badges.

    Args:
        session: Async database session.

    Returns:
        Number of badges created.
    """
    created = 0

    for badge_data in BADGES_DATA:
        # Check if badge already exists by code
        result = await session.execute(
            select(Badge).where(Badge.code == badge_data["code"])
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            badge = Badge(**badge_data)
            session.add(badge)
            created += 1
            logger.info(f"Created badge: {badge_data['code']} - {badge_data['name_en']}")
        else:
            logger.debug(f"Badge already exists: {badge_data['code']}")

    return created


async def seed_infractions(session: AsyncSession) -> int:
    """Seed infractions table with traffic violation types.

    Args:
        session: Async database session.

    Returns:
        Number of infractions created.
    """
    created = 0

    for infraction_data in INFRACTIONS_DATA:
        # Check if infraction already exists by code
        result = await session.execute(
            select(Infraction).where(Infraction.code == infraction_data["code"])
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            infraction = Infraction(**infraction_data)
            session.add(infraction)
            created += 1
            logger.info(f"Created infraction: {infraction_data['code']} - {infraction_data['name_en']}")
        else:
            logger.debug(f"Infraction already exists: {infraction_data['code']}")

    return created


async def seed_vehicle_types(session: AsyncSession) -> int:
    """Seed vehicle_types table with vehicle categories.

    Args:
        session: Async database session.

    Returns:
        Number of vehicle types created.
    """
    created = 0

    for vehicle_data in VEHICLE_TYPES_DATA:
        # Check if vehicle type already exists by code
        result = await session.execute(
            select(VehicleType).where(VehicleType.code == vehicle_data["code"])
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            vehicle_type = VehicleType(**vehicle_data)
            session.add(vehicle_type)
            created += 1
            logger.info(f"Created vehicle type: {vehicle_data['code']} - {vehicle_data['name_en']}")
        else:
            logger.debug(f"Vehicle type already exists: {vehicle_data['code']}")

    return created


async def seed_all() -> dict[str, int]:
    """Seed all tables with initial data.

    Returns:
        Dictionary with counts of created records per table.
    """
    logger.info("Starting database seed...")

    results = {
        "levels": 0,
        "badges": 0,
        "infractions": 0,
        "vehicle_types": 0,
    }

    async with async_session_maker() as session:
        try:
            # Seed all tables
            results["levels"] = await seed_levels(session)
            results["badges"] = await seed_badges(session)
            results["infractions"] = await seed_infractions(session)
            results["vehicle_types"] = await seed_vehicle_types(session)

            # Commit all changes
            await session.commit()

            logger.info("=" * 50)
            logger.info("Seed completed successfully!")
            logger.info(f"  Levels created: {results['levels']}")
            logger.info(f"  Badges created: {results['badges']}")
            logger.info(f"  Infractions created: {results['infractions']}")
            logger.info(f"  Vehicle types created: {results['vehicle_types']}")
            logger.info("=" * 50)

        except Exception as e:
            await session.rollback()
            logger.error(f"Seed failed: {e}")
            raise

    return results


async def main() -> None:
    """Main entry point for the seed script."""
    await seed_all()


if __name__ == "__main__":
    asyncio.run(main())
