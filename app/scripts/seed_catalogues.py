"""Seed catalogue/reference tables with initial data.

Populates all reference tables used by the Multando platform:
- Infractions (20 Colombian traffic violation types)
- Vehicle Types (9 vehicle categories)
- Levels (12 gamification tiers)
- Badges (12 achievement badges)

The script is fully idempotent: it uses INSERT ... ON CONFLICT DO UPDATE
so it can safely be re-run to update existing rows with new values.

Usage:
    cd services/api
    python -m app.scripts.seed_catalogues

Or via Docker:
    docker compose exec api python -m app.scripts.seed_catalogues

Or via Railway:
    railway run --service multando-backend python -m app.scripts.seed_catalogues
"""

import asyncio
import logging
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.enums import BadgeRarity, InfractionCategory, InfractionSeverity
from app.models.report import Infraction, VehicleType
from app.models.user import Badge, Level

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# INFRACTIONS DATA  (Colombian traffic code - Ley 769 de 2002)
# ============================================================
INFRACTIONS_DATA: list[dict[str, Any]] = [
    {
        "code": "SPD001",
        "name_en": "Speeding",
        "name_es": "Exceso de velocidad",
        "description_en": "Vehicle exceeding the posted speed limit.",
        "description_es": "Vehiculo excediendo el limite de velocidad establecido.",
        "category": InfractionCategory.SPEED,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 1,
    },
    {
        "code": "DRK001",
        "name_en": "Drunk Driving",
        "name_es": "Conduccion en estado de embriaguez",
        "description_en": "Driving under the influence of alcohol or drugs.",
        "description_es": "Conducir bajo los efectos del alcohol o sustancias psicoactivas.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.CRITICAL,
        "points_reward": 25,
        "multa_reward": Decimal("20.000000"),
        "sort_order": 2,
    },
    {
        "code": "PRK001",
        "name_en": "Illegal Parking",
        "name_es": "Estacionamiento ilegal",
        "description_en": "Vehicle parked in a prohibited zone.",
        "description_es": "Vehiculo estacionado en zona prohibida.",
        "category": InfractionCategory.PARKING,
        "severity": InfractionSeverity.LOW,
        "points_reward": 5,
        "multa_reward": Decimal("3.000000"),
        "sort_order": 3,
    },
    {
        "code": "RLT001",
        "name_en": "Running Red Light",
        "name_es": "Pasar semaforo en rojo",
        "description_en": "Vehicle passing through a red traffic light.",
        "description_es": "Vehiculo que pasa el semaforo en rojo.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 20,
        "multa_reward": Decimal("15.000000"),
        "sort_order": 4,
    },
    {
        "code": "STP001",
        "name_en": "Running Stop Sign",
        "name_es": "No respetar senal de pare",
        "description_en": "Failure to stop at a stop sign.",
        "description_es": "No detenerse ante la senal de pare.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 5,
    },
    {
        "code": "LNE001",
        "name_en": "Illegal Lane Change",
        "name_es": "Cambio de carril ilegal",
        "description_en": "Changing lanes without signaling or in a prohibited zone.",
        "description_es": "Cambio de carril sin senalizar o en zona prohibida.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("8.000000"),
        "sort_order": 6,
    },
    {
        "code": "PHN001",
        "name_en": "Phone While Driving",
        "name_es": "Uso de celular conduciendo",
        "description_en": "Using a mobile phone while driving.",
        "description_es": "Uso del telefono celular mientras se conduce.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 7,
    },
    {
        "code": "SBT001",
        "name_en": "No Seatbelt",
        "name_es": "No uso de cinturon",
        "description_en": "Driver or passenger not wearing a seatbelt.",
        "description_es": "Conductor o pasajero sin cinturon de seguridad.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 8,
    },
    {
        "code": "HLM001",
        "name_en": "No Helmet (Motorcycle)",
        "name_es": "No uso de casco",
        "description_en": "Motorcycle rider or passenger without a helmet.",
        "description_es": "Motociclista o pasajero sin casco de proteccion.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("8.000000"),
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
        "code": "SWK001",
        "name_en": "Driving on Sidewalk",
        "name_es": "Conducir por el anden",
        "description_en": "Driving a motor vehicle on the sidewalk or pedestrian area.",
        "description_es": "Conducir un vehiculo motorizado por el anden o zona peatonal.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 20,
        "multa_reward": Decimal("15.000000"),
        "sort_order": 11,
    },
    {
        "code": "WRG001",
        "name_en": "Wrong Way Driving",
        "name_es": "Conducir en contravia",
        "description_en": "Driving against the designated traffic direction.",
        "description_es": "Conducir en sentido contrario al establecido.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.CRITICAL,
        "points_reward": 25,
        "multa_reward": Decimal("20.000000"),
        "sort_order": 12,
    },
    {
        "code": "OVT001",
        "name_en": "Illegal Overtaking",
        "name_es": "Adelantamiento ilegal",
        "description_en": "Overtaking another vehicle in a prohibited zone.",
        "description_es": "Adelantar otro vehiculo en zona prohibida.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 13,
    },
    {
        "code": "NLT001",
        "name_en": "No Lights at Night",
        "name_es": "Sin luces en la noche",
        "description_en": "Driving at night without headlights or tail lights on.",
        "description_es": "Conducir de noche sin luces delanteras o traseras encendidas.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 14,
    },
    {
        "code": "ZBR001",
        "name_en": "Blocking Zebra Crossing",
        "name_es": "Bloquear paso de cebra",
        "description_en": "Stopping on or blocking a pedestrian zebra crossing.",
        "description_es": "Detenerse sobre o bloquear un paso de cebra peatonal.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.LOW,
        "points_reward": 5,
        "multa_reward": Decimal("3.000000"),
        "sort_order": 15,
    },
    {
        "code": "HRN001",
        "name_en": "Excessive Honking",
        "name_es": "Uso excesivo de bocina",
        "description_en": "Unnecessary or excessive use of the vehicle horn.",
        "description_es": "Uso innecesario o excesivo de la bocina del vehiculo.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.LOW,
        "points_reward": 3,
        "multa_reward": Decimal("2.000000"),
        "sort_order": 16,
    },
    {
        "code": "SMK001",
        "name_en": "Excessive Smoke/Emissions",
        "name_es": "Emisiones excesivas",
        "description_en": "Vehicle producing excessive smoke or pollutant emissions.",
        "description_es": "Vehiculo que produce humo o emisiones contaminantes excesivas.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("8.000000"),
        "sort_order": 17,
    },
    {
        "code": "NIS001",
        "name_en": "No Insurance",
        "name_es": "Sin seguro obligatorio",
        "description_en": "Operating a vehicle without mandatory insurance (SOAT).",
        "description_es": "Conducir un vehiculo sin seguro obligatorio (SOAT).",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.HIGH,
        "points_reward": 15,
        "multa_reward": Decimal("10.000000"),
        "sort_order": 18,
    },
    {
        "code": "EXP001",
        "name_en": "Expired License Plate",
        "name_es": "Placa vencida",
        "description_en": "Vehicle with expired license plate or registration.",
        "description_es": "Vehiculo con placa o matricula vencida.",
        "category": InfractionCategory.SAFETY,
        "severity": InfractionSeverity.MEDIUM,
        "points_reward": 10,
        "multa_reward": Decimal("5.000000"),
        "sort_order": 19,
    },
    {
        "code": "OTH001",
        "name_en": "Other Violation",
        "name_es": "Otra infraccion",
        "description_en": "Other traffic violation not listed in specific categories.",
        "description_es": "Otra infraccion de transito no listada en categorias especificas.",
        "category": InfractionCategory.BEHAVIOR,
        "severity": InfractionSeverity.LOW,
        "points_reward": 5,
        "multa_reward": Decimal("3.000000"),
        "sort_order": 20,
    },
]


# ============================================================
# VEHICLE TYPES DATA
# ============================================================
VEHICLE_TYPES_DATA: list[dict[str, Any]] = [
    {
        "code": "CAR",
        "name_en": "Car",
        "name_es": "Automovil",
        "icon": "car",
        "plate_pattern": r"^[A-Z]{3}[0-9]{3,4}$",
        "requires_plate": True,
        "sort_order": 1,
    },
    {
        "code": "MOTO",
        "name_en": "Motorcycle",
        "name_es": "Motocicleta",
        "icon": "motorcycle",
        "plate_pattern": r"^[A-Z]{3}[0-9]{2}[A-Z]$",
        "requires_plate": True,
        "sort_order": 2,
    },
    {
        "code": "TRUCK",
        "name_en": "Truck",
        "name_es": "Camion",
        "icon": "truck",
        "plate_pattern": r"^[A-Z]{3}[0-9]{3,4}$",
        "requires_plate": True,
        "sort_order": 3,
    },
    {
        "code": "BUS",
        "name_en": "Bus",
        "name_es": "Bus",
        "icon": "bus",
        "plate_pattern": r"^[A-Z]{3}[0-9]{3,4}$",
        "requires_plate": True,
        "sort_order": 4,
    },
    {
        "code": "VAN",
        "name_en": "Van",
        "name_es": "Camioneta",
        "icon": "van",
        "plate_pattern": r"^[A-Z]{3}[0-9]{3,4}$",
        "requires_plate": True,
        "sort_order": 5,
    },
    {
        "code": "TAXI",
        "name_en": "Taxi",
        "name_es": "Taxi",
        "icon": "taxi",
        "plate_pattern": r"^[A-Z]{3}[0-9]{3,4}$",
        "requires_plate": True,
        "sort_order": 6,
    },
    {
        "code": "BIKE",
        "name_en": "Bicycle",
        "name_es": "Bicicleta",
        "icon": "bicycle",
        "plate_pattern": None,
        "requires_plate": False,
        "sort_order": 7,
    },
    {
        "code": "SCOOTER",
        "name_en": "Electric Scooter",
        "name_es": "Patineta electrica",
        "icon": "scooter",
        "plate_pattern": None,
        "requires_plate": False,
        "sort_order": 8,
    },
    {
        "code": "OTHER",
        "name_en": "Other",
        "name_es": "Otro",
        "icon": "other",
        "plate_pattern": None,
        "requires_plate": False,
        "sort_order": 9,
    },
]


# ============================================================
# LEVELS DATA  (gamification tiers)
# ============================================================
LEVELS_DATA: list[dict[str, Any]] = [
    {
        "tier": 1,
        "title_en": "Newcomer",
        "title_es": "Novato",
        "description_en": "Welcome to Multando! You are just starting your journey.",
        "description_es": "Bienvenido a Multando! Acabas de comenzar tu camino.",
        "min_points": 0,
        "multa_bonus": Decimal("0.00"),
    },
    {
        "tier": 2,
        "title_en": "Observer",
        "title_es": "Observador",
        "description_en": "You are paying attention and making a difference.",
        "description_es": "Estas atento y haciendo la diferencia.",
        "min_points": 50,
        "multa_bonus": Decimal("2.00"),
    },
    {
        "tier": 3,
        "title_en": "Reporter",
        "title_es": "Reportero",
        "description_en": "Your reports help keep roads safe.",
        "description_es": "Tus reportes ayudan a mantener las vias seguras.",
        "min_points": 150,
        "multa_bonus": Decimal("5.00"),
    },
    {
        "tier": 4,
        "title_en": "Contributor",
        "title_es": "Colaborador",
        "description_en": "A consistent contributor to road safety.",
        "description_es": "Un colaborador constante de la seguridad vial.",
        "min_points": 300,
        "multa_bonus": Decimal("8.00"),
    },
    {
        "tier": 5,
        "title_en": "Guardian",
        "title_es": "Guardian",
        "description_en": "Guarding the roads with dedication.",
        "description_es": "Protegiendo las vias con dedicacion.",
        "min_points": 500,
        "multa_bonus": Decimal("10.00"),
    },
    {
        "tier": 6,
        "title_en": "Protector",
        "title_es": "Protector",
        "description_en": "A protector of public safety on the roads.",
        "description_es": "Un protector de la seguridad publica en las vias.",
        "min_points": 800,
        "multa_bonus": Decimal("12.00"),
    },
    {
        "tier": 7,
        "title_en": "Civic Guardian",
        "title_es": "Guardian Civico",
        "description_en": "A civic guardian leading the community by example.",
        "description_es": "Un guardian civico liderando la comunidad con el ejemplo.",
        "min_points": 1200,
        "multa_bonus": Decimal("15.00"),
    },
    {
        "tier": 8,
        "title_en": "Defender",
        "title_es": "Defensor",
        "description_en": "Defending road safety with unwavering commitment.",
        "description_es": "Defendiendo la seguridad vial con compromiso inquebrantable.",
        "min_points": 1800,
        "multa_bonus": Decimal("18.00"),
    },
    {
        "tier": 9,
        "title_en": "Champion",
        "title_es": "Campeon",
        "description_en": "A champion of safe and respectful driving.",
        "description_es": "Un campeon de la conduccion segura y respetuosa.",
        "min_points": 2500,
        "multa_bonus": Decimal("20.00"),
    },
    {
        "tier": 10,
        "title_en": "Legend",
        "title_es": "Leyenda",
        "description_en": "Your contributions are legendary.",
        "description_es": "Tus contribuciones son legendarias.",
        "min_points": 3500,
        "multa_bonus": Decimal("25.00"),
    },
    {
        "tier": 15,
        "title_en": "Sentinel",
        "title_es": "Centinela",
        "description_en": "An ever-watchful sentinel of road safety.",
        "description_es": "Un centinela siempre vigilante de la seguridad vial.",
        "min_points": 7500,
        "multa_bonus": Decimal("30.00"),
    },
    {
        "tier": 20,
        "title_en": "Master",
        "title_es": "Maestro",
        "description_en": "The highest honor. A true master of civic responsibility.",
        "description_es": "El mayor honor. Un verdadero maestro de la responsabilidad civica.",
        "min_points": 15000,
        "multa_bonus": Decimal("35.00"),
    },
]


# ============================================================
# BADGES DATA
# ============================================================
BADGES_DATA: list[dict[str, Any]] = [
    {
        "code": "FIRST_REPORT",
        "name_en": "First Reporter",
        "name_es": "Primer Reporte",
        "description_en": "Submit your first report",
        "description_es": "Envia tu primer reporte",
        "rarity": BadgeRarity.COMMON,
        "multa_reward": Decimal("5.000000"),
        "is_nft": False,
        "criteria": {"reports_submitted": 1},
    },
    {
        "code": "FIVE_REPORTS",
        "name_en": "Active Citizen",
        "name_es": "Ciudadano Activo",
        "description_en": "Submit 5 reports",
        "description_es": "Envia 5 reportes",
        "rarity": BadgeRarity.COMMON,
        "multa_reward": Decimal("10.000000"),
        "is_nft": False,
        "criteria": {"reports_submitted": 5},
    },
    {
        "code": "TWENTY_REPORTS",
        "name_en": "Watchdog",
        "name_es": "Vigilante",
        "description_en": "Submit 20 reports",
        "description_es": "Envia 20 reportes",
        "rarity": BadgeRarity.RARE,
        "multa_reward": Decimal("25.000000"),
        "is_nft": True,
        "criteria": {"reports_submitted": 20},
    },
    {
        "code": "FIFTY_REPORTS",
        "name_en": "Sentinel",
        "name_es": "Centinela",
        "description_en": "Submit 50 reports",
        "description_es": "Envia 50 reportes",
        "rarity": BadgeRarity.EPIC,
        "multa_reward": Decimal("50.000000"),
        "is_nft": True,
        "criteria": {"reports_submitted": 50},
    },
    {
        "code": "FIRST_VERIFY",
        "name_en": "Community Helper",
        "name_es": "Ayudante",
        "description_en": "Verify your first report",
        "description_es": "Verifica tu primer reporte",
        "rarity": BadgeRarity.COMMON,
        "multa_reward": Decimal("5.000000"),
        "is_nft": False,
        "criteria": {"verifications_done": 1},
    },
    {
        "code": "TEN_VERIFIES",
        "name_en": "Trusted Verifier",
        "name_es": "Verificador Confiable",
        "description_en": "Verify 10 reports",
        "description_es": "Verifica 10 reportes",
        "rarity": BadgeRarity.UNCOMMON,
        "multa_reward": Decimal("15.000000"),
        "is_nft": False,
        "criteria": {"verifications_done": 10},
    },
    {
        "code": "STREAK_7",
        "name_en": "Weekly Warrior",
        "name_es": "Guerrero Semanal",
        "description_en": "7-day reporting streak",
        "description_es": "Racha de 7 dias reportando",
        "rarity": BadgeRarity.UNCOMMON,
        "multa_reward": Decimal("10.000000"),
        "is_nft": False,
        "criteria": {"streak_days": 7},
    },
    {
        "code": "STREAK_30",
        "name_en": "Monthly Master",
        "name_es": "Maestro Mensual",
        "description_en": "30-day reporting streak",
        "description_es": "Racha de 30 dias reportando",
        "rarity": BadgeRarity.EPIC,
        "multa_reward": Decimal("50.000000"),
        "is_nft": True,
        "criteria": {"streak_days": 30},
    },
    {
        "code": "MULTI_CITY",
        "name_en": "Road Explorer",
        "name_es": "Explorador Vial",
        "description_en": "Report in 3+ cities",
        "description_es": "Reporta en 3+ ciudades",
        "rarity": BadgeRarity.RARE,
        "multa_reward": Decimal("20.000000"),
        "is_nft": True,
        "criteria": {"unique_cities": 3},
    },
    {
        "code": "STAKER",
        "name_en": "Token Staker",
        "name_es": "Staker",
        "description_en": "Stake MULTA tokens",
        "description_es": "Haz stake de tokens MULTA",
        "rarity": BadgeRarity.COMMON,
        "multa_reward": Decimal("5.000000"),
        "is_nft": False,
        "criteria": {"has_staked": True},
    },
    {
        "code": "TOP_10",
        "name_en": "Elite Guardian",
        "name_es": "Guardian Elite",
        "description_en": "Reach top 10 leaderboard",
        "description_es": "Alcanza el top 10 de la clasificacion",
        "rarity": BadgeRarity.LEGENDARY,
        "multa_reward": Decimal("100.000000"),
        "is_nft": True,
        "criteria": {"leaderboard_rank": 10},
    },
    {
        "code": "REFERRAL_5",
        "name_en": "Recruiter",
        "name_es": "Reclutador",
        "description_en": "Refer 5 friends",
        "description_es": "Refiere 5 amigos",
        "rarity": BadgeRarity.UNCOMMON,
        "multa_reward": Decimal("15.000000"),
        "is_nft": False,
        "criteria": {"referrals": 5},
    },
]


# ============================================================
# Upsert helpers
# ============================================================

async def _upsert_infractions(session: AsyncSession) -> int:
    """Upsert all infraction rows. Returns count of affected rows."""
    count = 0
    for data in INFRACTIONS_DATA:
        # Convert enums to their string values for the INSERT statement
        row = {
            **data,
            "category": data["category"].value,
            "severity": data["severity"].value,
            "is_active": True,
        }
        stmt = (
            pg_insert(Infraction)
            .values(**row)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name_en": row["name_en"],
                    "name_es": row["name_es"],
                    "description_en": row["description_en"],
                    "description_es": row["description_es"],
                    "category": row["category"],
                    "severity": row["severity"],
                    "points_reward": row["points_reward"],
                    "multa_reward": row["multa_reward"],
                    "sort_order": row["sort_order"],
                    "is_active": True,
                },
            )
        )
        await session.execute(stmt)
        count += 1
        logger.info("  [%d/%d] %s - %s", count, len(INFRACTIONS_DATA), data["code"], data["name_en"])
    return count


async def _upsert_vehicle_types(session: AsyncSession) -> int:
    """Upsert all vehicle type rows. Returns count of affected rows."""
    count = 0
    for data in VEHICLE_TYPES_DATA:
        stmt = (
            pg_insert(VehicleType)
            .values(**data)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name_en": data["name_en"],
                    "name_es": data["name_es"],
                    "icon": data["icon"],
                    "plate_pattern": data["plate_pattern"],
                    "requires_plate": data["requires_plate"],
                    "sort_order": data["sort_order"],
                },
            )
        )
        await session.execute(stmt)
        count += 1
        logger.info("  [%d/%d] %s - %s", count, len(VEHICLE_TYPES_DATA), data["code"], data["name_en"])
    return count


async def _upsert_levels(session: AsyncSession) -> int:
    """Upsert all level rows. Returns count of affected rows."""
    count = 0
    for data in LEVELS_DATA:
        stmt = (
            pg_insert(Level)
            .values(**data)
            .on_conflict_do_update(
                index_elements=["tier"],
                set_={
                    "title_en": data["title_en"],
                    "title_es": data["title_es"],
                    "description_en": data["description_en"],
                    "description_es": data["description_es"],
                    "min_points": data["min_points"],
                    "multa_bonus": data["multa_bonus"],
                },
            )
        )
        await session.execute(stmt)
        count += 1
        logger.info(
            "  [%d/%d] Tier %d - %s",
            count,
            len(LEVELS_DATA),
            data["tier"],
            data["title_en"],
        )
    return count


async def _upsert_badges(session: AsyncSession) -> int:
    """Upsert all badge rows. Returns count of affected rows."""
    count = 0
    for data in BADGES_DATA:
        row = {
            **data,
            "rarity": data["rarity"].value,
        }
        stmt = (
            pg_insert(Badge)
            .values(**row)
            .on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "name_en": row["name_en"],
                    "name_es": row["name_es"],
                    "description_en": row["description_en"],
                    "description_es": row["description_es"],
                    "rarity": row["rarity"],
                    "multa_reward": row["multa_reward"],
                    "is_nft": row["is_nft"],
                    "criteria": row["criteria"],
                },
            )
        )
        await session.execute(stmt)
        count += 1
        logger.info("  [%d/%d] %s - %s", count, len(BADGES_DATA), data["code"], data["name_en"])
    return count


# ============================================================
# Main entry points
# ============================================================

async def seed_catalogues() -> dict[str, int]:
    """Seed all catalogue/reference tables.

    Returns:
        Dictionary mapping table name to number of rows upserted.
    """
    logger.info("=" * 60)
    logger.info("Multando Catalogue Seed")
    logger.info("=" * 60)

    results: dict[str, int] = {}

    async with async_session_maker() as session:
        try:
            logger.info("")
            logger.info("Seeding infractions (%d rows)...", len(INFRACTIONS_DATA))
            results["infractions"] = await _upsert_infractions(session)

            logger.info("")
            logger.info("Seeding vehicle types (%d rows)...", len(VEHICLE_TYPES_DATA))
            results["vehicle_types"] = await _upsert_vehicle_types(session)

            logger.info("")
            logger.info("Seeding levels (%d rows)...", len(LEVELS_DATA))
            results["levels"] = await _upsert_levels(session)

            logger.info("")
            logger.info("Seeding badges (%d rows)...", len(BADGES_DATA))
            results["badges"] = await _upsert_badges(session)

            await session.commit()

            logger.info("")
            logger.info("=" * 60)
            logger.info("Seed completed successfully!")
            for table, count in results.items():
                logger.info("  %-20s %d rows", table, count)
            logger.info("=" * 60)

        except Exception:
            await session.rollback()
            logger.exception("Seed failed - transaction rolled back")
            raise

    return results


async def main() -> None:
    """CLI entry point."""
    try:
        await seed_catalogues()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
