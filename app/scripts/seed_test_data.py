"""Seed test data for sandbox/development environment.

Generates realistic Bogota-based test data including users, authorities,
reports, activities, and token transactions so SDK developers can
immediately see real-looking data when they hit the sandbox API.

Usage:
    cd services/api
    python -m app.scripts.seed_test_data

Or via Railway:
    railway run --service multando-backend python -m app.scripts.seed_test_data

WARNING: This will create test data. Only run in sandbox/development!
"""

import asyncio
import hashlib
import logging
import os
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_maker
from app.models import (
    Activity,
    ActivityType,
    ApiKey,
    Authority,
    AuthorityRole,
    AuthorityUser,
    AuthorityWebhook,
    City,
    CustodialWallet,
    Evidence,
    EvidenceType,
    HotWalletLedger,
    Infraction,
    Report,
    ReportSource,
    ReportStatus,
    StakingPosition,
    TokenTransaction,
    TokenTxType,
    TxStatus,
    User,
    UserRole,
    VehicleCategory,
    VehicleType,
    WalletType,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_PASSWORD = "test123"
TEST_PASSWORD_HASH = pwd_context.hash(TEST_PASSWORD)

# Sentinel: all test users share this email domain so we can detect them
TEST_EMAIL_DOMAIN = "sandbox.multando.dev"

STORAGE_BASE = settings.STORAGE_BASE_URL.rstrip("/")

# ---------------------------------------------------------------------------
# Bogota locations
# ---------------------------------------------------------------------------

BOGOTA_LOCATIONS: list[dict[str, Any]] = [
    {"name": "Chapinero", "lat": 4.6486, "lng": -74.0628, "address": "Calle 53 con Carrera 13, Chapinero"},
    {"name": "Usaquen", "lat": 4.6964, "lng": -74.0310, "address": "Calle 119 con Carrera 7, Usaquen"},
    {"name": "Zona T", "lat": 4.6680, "lng": -74.0524, "address": "Calle 82 con Carrera 13, Zona T"},
    {"name": "Calle 80", "lat": 4.6837, "lng": -74.0810, "address": "Av. Calle 80 con Carrera 68"},
    {"name": "Autopista Norte", "lat": 4.7565, "lng": -74.0430, "address": "Autopista Norte Km 12"},
    {"name": "Centro Historico", "lat": 4.5981, "lng": -74.0761, "address": "Carrera 7 con Calle 11, La Candelaria"},
    {"name": "Kennedy", "lat": 4.6281, "lng": -74.1519, "address": "Av. 1 de Mayo con Carrera 80"},
    {"name": "Suba", "lat": 4.7416, "lng": -74.0836, "address": "Av. Suba con Calle 140"},
    {"name": "Teusaquillo", "lat": 4.6324, "lng": -74.0769, "address": "Calle 45 con Carrera 30"},
    {"name": "Bosa", "lat": 4.5881, "lng": -74.1891, "address": "Av. Agoberto Mejia, Bosa"},
    {"name": "Fontibon", "lat": 4.6731, "lng": -74.1469, "address": "Av. Centenario con Carrera 100"},
    {"name": "Engativa", "lat": 4.7066, "lng": -74.1107, "address": "Calle 80 con Av. Boyaca"},
    {"name": "Puente Aranda", "lat": 4.6222, "lng": -74.1028, "address": "Av. de las Americas con Carrera 50"},
    {"name": "Barrios Unidos", "lat": 4.6661, "lng": -74.0757, "address": "Calle 63 con Carrera 24"},
    {"name": "Santa Fe", "lat": 4.6115, "lng": -74.0714, "address": "Carrera 10 con Calle 19, San Victorino"},
]

# ---------------------------------------------------------------------------
# Colombian test user data
# ---------------------------------------------------------------------------

# fmt: off
TEST_USERS: list[dict[str, Any]] = [
    # 1 admin
    {"email": f"admin@{TEST_EMAIL_DOMAIN}", "username": "admin_multando", "display_name": "Luis Fernando Torres", "phone": "+573001000001", "role": UserRole.ADMIN},
    # 2 authority admins
    {"email": f"auth.admin1@{TEST_EMAIL_DOMAIN}", "username": "smb_admin_garcia", "display_name": "Ricardo Garcia Mendez", "phone": "+573001000002", "role": UserRole.AUTHORITY},
    {"email": f"auth.admin2@{TEST_EMAIL_DOMAIN}", "username": "smb_admin_herrera", "display_name": "Claudia Patricia Herrera", "phone": "+573001000003", "role": UserRole.AUTHORITY},
    # 3 authority analysts
    {"email": f"auth.analyst1@{TEST_EMAIL_DOMAIN}", "username": "smb_analyst_rojas", "display_name": "Andres Felipe Rojas", "phone": "+573001000004", "role": UserRole.AUTHORITY},
    {"email": f"auth.analyst2@{TEST_EMAIL_DOMAIN}", "username": "smb_analyst_moreno", "display_name": "Laura Marcela Moreno", "phone": "+573001000005", "role": UserRole.AUTHORITY},
    {"email": f"auth.analyst3@{TEST_EMAIL_DOMAIN}", "username": "smb_analyst_castro", "display_name": "Diego Alejandro Castro", "phone": "+573001000006", "role": UserRole.AUTHORITY},
    # 14 citizens
    {"email": f"maria.garcia@{TEST_EMAIL_DOMAIN}", "username": "mariagarcia", "display_name": "Maria Garcia Lopez", "phone": "+573101000001", "role": UserRole.CITIZEN},
    {"email": f"carlos.rodriguez@{TEST_EMAIL_DOMAIN}", "username": "carlosrodriguez", "display_name": "Carlos Andres Rodriguez", "phone": "+573101000002", "role": UserRole.CITIZEN},
    {"email": f"ana.lopez@{TEST_EMAIL_DOMAIN}", "username": "anasofia_lopez", "display_name": "Ana Sofia Lopez", "phone": "+573101000003", "role": UserRole.CITIZEN},
    {"email": f"juan.martinez@{TEST_EMAIL_DOMAIN}", "username": "juanmartinez", "display_name": "Juan Pablo Martinez", "phone": "+573101000004", "role": UserRole.CITIZEN},
    {"email": f"valentina.diaz@{TEST_EMAIL_DOMAIN}", "username": "valentinadiaz", "display_name": "Valentina Diaz Ortiz", "phone": "+573101000005", "role": UserRole.CITIZEN},
    {"email": f"santiago.vargas@{TEST_EMAIL_DOMAIN}", "username": "santiagovargas", "display_name": "Santiago Vargas Perez", "phone": "+573101000006", "role": UserRole.CITIZEN},
    {"email": f"camila.torres@{TEST_EMAIL_DOMAIN}", "username": "camilatorres", "display_name": "Camila Andrea Torres", "phone": "+573101000007", "role": UserRole.CITIZEN},
    {"email": f"daniel.ramirez@{TEST_EMAIL_DOMAIN}", "username": "danielramirez", "display_name": "Daniel Felipe Ramirez", "phone": "+573101000008", "role": UserRole.CITIZEN},
    {"email": f"isabella.ruiz@{TEST_EMAIL_DOMAIN}", "username": "isabellaruiz", "display_name": "Isabella Ruiz Gomez", "phone": "+573101000009", "role": UserRole.CITIZEN},
    {"email": f"samuel.gomez@{TEST_EMAIL_DOMAIN}", "username": "samuelgomez", "display_name": "Samuel Gomez Castro", "phone": "+573101000010", "role": UserRole.CITIZEN},
    {"email": f"sofia.hernandez@{TEST_EMAIL_DOMAIN}", "username": "sofiahernandez", "display_name": "Sofia Hernandez Mejia", "phone": "+573101000011", "role": UserRole.CITIZEN},
    {"email": f"mateo.castro@{TEST_EMAIL_DOMAIN}", "username": "mateocastro", "display_name": "Mateo Castro Rios", "phone": "+573101000012", "role": UserRole.CITIZEN},
    {"email": f"gabriela.mendez@{TEST_EMAIL_DOMAIN}", "username": "gabrielamendez", "display_name": "Gabriela Mendez Pineda", "phone": "+573101000013", "role": UserRole.CITIZEN},
    {"email": f"nicolas.pineda@{TEST_EMAIL_DOMAIN}", "username": "nicolaspineda", "display_name": "Nicolas Pineda Cardenas", "phone": "+573101000014", "role": UserRole.CITIZEN},
]
# fmt: on


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_short_id() -> str:
    """Generate a 12-char alphanumeric short id like RPT-XXXXXXXX."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=8))
    return f"RPT-{suffix}"


def _random_plate(vehicle_code: str) -> str:
    """Generate a realistic Colombian license plate."""
    letters = string.ascii_uppercase
    if vehicle_code == "MOTO":
        # Motorcycle: ABC12A
        return (
            random.choice(letters)
            + random.choice(letters)
            + random.choice(letters)
            + str(random.randint(0, 9))
            + str(random.randint(0, 9))
            + random.choice(letters)
        )
    if vehicle_code == "TAXI":
        # Taxi: TAX + 3 digits or SBC pattern
        prefix = random.choice(["TAX", "SBC", "SOA", "SOC"])
        return prefix + str(random.randint(100, 999))
    if vehicle_code == "BUS":
        prefix = random.choice(["SBC", "SOA", "SNA", "SNB"])
        return prefix + str(random.randint(100, 999))
    # Private car: ABC123 or newer ABC12D
    prefix = (
        random.choice(letters) + random.choice(letters) + random.choice(letters)
    )
    if random.random() < 0.4:
        # Newer format: ABC12D
        return prefix + str(random.randint(10, 99)) + random.choice(letters)
    # Classic format: ABC123
    return prefix + str(random.randint(100, 999))


def _fake_public_key() -> str:
    """Generate a fake Solana-ish public key (base58-like, 44 chars)."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=44))


def _fake_encrypted_bytes(length: int = 64) -> bytes:
    """Generate fake encrypted bytes for custodial wallet fields."""
    return os.urandom(length)


def _sha256(value: str) -> str:
    """Return hex SHA-256 digest of a string."""
    return hashlib.sha256(value.encode()).hexdigest()


def _jitter(base_lat: float, base_lng: float) -> tuple[float, float]:
    """Add small random jitter to coordinates (~200m radius)."""
    lat = base_lat + random.uniform(-0.002, 0.002)
    lng = base_lng + random.uniform(-0.002, 0.002)
    return round(lat, 6), round(lng, 6)


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------


async def _check_already_seeded(session: AsyncSession) -> bool:
    """Return True if test data already exists."""
    result = await session.execute(
        select(User).where(User.email == f"admin@{TEST_EMAIL_DOMAIN}")
    )
    return result.scalar_one_or_none() is not None


async def seed_users(session: AsyncSession) -> list[User]:
    """Create 20 test users. Returns list of created User objects."""
    users: list[User] = []
    for udata in TEST_USERS:
        user = User(
            id=uuid.uuid4(),
            email=udata["email"],
            username=udata["username"],
            display_name=udata["display_name"],
            phone_number=udata["phone"],
            password_hash=TEST_PASSWORD_HASH,
            wallet_type=WalletType.CUSTODIAL,
            role=udata["role"],
            locale="es",
            is_active=True,
            is_verified=True,
            points=random.randint(0, 200) if udata["role"] == UserRole.CITIZEN else 0,
            reputation_score=Decimal(str(round(random.uniform(80.0, 100.0), 2))),
        )
        session.add(user)
        users.append(user)
    await session.flush()
    logger.info(f"Created {len(users)} test users")
    return users


async def seed_custodial_wallets(
    session: AsyncSession, users: list[User]
) -> list[CustodialWallet]:
    """Create a custodial wallet for each user."""
    wallets: list[CustodialWallet] = []
    for user in users:
        wallet = CustodialWallet(
            user_id=user.id,
            public_key=_fake_public_key(),
            encrypted_private_key=_fake_encrypted_bytes(64),
            encrypted_dek=_fake_encrypted_bytes(32),
            iv=_fake_encrypted_bytes(16),
            encryption_version=1,
        )
        session.add(wallet)
        wallets.append(wallet)
    await session.flush()
    logger.info(f"Created {len(wallets)} custodial wallets")
    return wallets


async def seed_hot_wallet_ledger(
    session: AsyncSession, users: list[User]
) -> None:
    """Create hot wallet ledger entries for each user (starting at 0)."""
    for user in users:
        ledger = HotWalletLedger(
            user_id=user.id,
            balance=Decimal("0.000000"),
        )
        session.add(ledger)
    await session.flush()
    logger.info(f"Created {len(users)} hot wallet ledger entries")


async def seed_authority(
    session: AsyncSession,
    authority_users: list[User],
    bogota_city_id: int,
) -> Authority:
    """Create the test authority and assign staff."""
    authority = Authority(
        name="Secretaria de Movilidad de Bogota",
        code="SMB",
        country="CO",
        city="Bogota",
        city_id=bogota_city_id,
        subscription_tier="premium",
        contact_email=f"contacto@{TEST_EMAIL_DOMAIN}",
        contact_name="Ricardo Garcia Mendez",
        rate_limit=5000,
    )
    session.add(authority)
    await session.flush()

    # Assign staff roles
    role_map = {
        0: AuthorityRole.ADMIN,   # auth.admin1
        1: AuthorityRole.ADMIN,   # auth.admin2
        2: AuthorityRole.ANALYST, # auth.analyst1
        3: AuthorityRole.ANALYST, # auth.analyst2
        4: AuthorityRole.ANALYST, # auth.analyst3
    }
    for idx, user in enumerate(authority_users):
        au = AuthorityUser(
            authority_id=authority.id,
            user_id=user.id,
            role=role_map.get(idx, AuthorityRole.VIEWER),
        )
        session.add(au)
    await session.flush()

    logger.info(
        f"Created authority '{authority.name}' (id={authority.id}) "
        f"with {len(authority_users)} staff"
    )
    return authority


async def seed_webhooks(
    session: AsyncSession, authority: Authority
) -> list[AuthorityWebhook]:
    """Create 2 inactive test webhooks."""
    webhooks_data = [
        {
            "url": "https://webhook.sandbox.multando.dev/reports",
            "secret": "whsec_test_sandbox_secret_001",
            "events": ["report.created", "report.verified", "report.rejected"],
            "is_active": False,
        },
        {
            "url": "https://webhook.sandbox.multando.dev/analytics",
            "secret": "whsec_test_sandbox_secret_002",
            "events": ["report.verified", "report.disputed"],
            "is_active": False,
        },
    ]
    webhooks: list[AuthorityWebhook] = []
    for wdata in webhooks_data:
        wh = AuthorityWebhook(authority_id=authority.id, **wdata)
        session.add(wh)
        webhooks.append(wh)
    await session.flush()
    logger.info(f"Created {len(webhooks)} webhooks (inactive)")
    return webhooks


async def seed_reports(
    session: AsyncSession,
    citizen_users: list[User],
    authority_analysts: list[User],
    bogota_city_id: int,
) -> list[Report]:
    """Create 50 test reports spread across Bogota."""
    # Fetch infractions and vehicle types from the catalogue
    infraction_rows = (await session.execute(select(Infraction))).scalars().all()
    vehicle_type_rows = (await session.execute(select(VehicleType))).scalars().all()

    if not infraction_rows or not vehicle_type_rows:
        logger.error(
            "Infractions or vehicle types not found. "
            "Run the catalogue seed first: python -m app.scripts.seed"
        )
        return []

    # Vehicle types that require plates (for generating plates)
    plate_vehicles = {vt.code: vt for vt in vehicle_type_rows if vt.requires_plate}
    no_plate_vehicles = [vt for vt in vehicle_type_rows if not vt.requires_plate]

    now = datetime.now(timezone.utc)

    # Status distribution: 15 pending, 25 verified, 7 rejected, 3 disputed
    statuses: list[ReportStatus] = (
        [ReportStatus.PENDING] * 15
        + [ReportStatus.VERIFIED] * 25
        + [ReportStatus.REJECTED] * 7
        + [ReportStatus.DISPUTED] * 3
    )
    random.shuffle(statuses)

    sources = [ReportSource.MOBILE, ReportSource.WEB, ReportSource.WHATSAPP, ReportSource.SDK]
    source_weights = [0.50, 0.25, 0.15, 0.10]

    reports: list[Report] = []
    evidence_count = 0

    for i in range(50):
        status = statuses[i]
        location = random.choice(BOGOTA_LOCATIONS)
        lat, lng = _jitter(location["lat"], location["lng"])
        infraction = random.choice(infraction_rows)

        # Pick a vehicle type (weighted: 70% plated, 30% no-plate)
        if random.random() < 0.7 and plate_vehicles:
            vt = random.choice(list(plate_vehicles.values()))
            plate = _random_plate(vt.code)
            v_category = (
                VehicleCategory.PUBLIC
                if vt.code in ("TAXI", "BUS")
                else VehicleCategory.PRIVATE
            )
        elif no_plate_vehicles:
            vt = random.choice(no_plate_vehicles)
            plate = None
            v_category = VehicleCategory.PRIVATE
        else:
            vt = random.choice(vehicle_type_rows)
            plate = _random_plate(vt.code) if vt.requires_plate else None
            v_category = VehicleCategory.PRIVATE

        # Spread over last 30 days
        days_ago = random.randint(0, 30)
        hours_offset = random.randint(6, 22)  # daytime incidents
        incident_dt = now - timedelta(days=days_ago, hours=random.randint(0, 12))
        incident_dt = incident_dt.replace(hour=hours_offset, minute=random.randint(0, 59))

        created_at = incident_dt + timedelta(minutes=random.randint(5, 120))
        reporter = random.choice(citizen_users)
        source = random.choices(sources, weights=source_weights, k=1)[0]

        report = Report(
            id=uuid.uuid4(),
            short_id=_random_short_id(),
            reporter_id=reporter.id,
            source=source,
            infraction_id=infraction.id,
            vehicle_plate=plate,
            vehicle_type_id=vt.id,
            vehicle_category=v_category,
            latitude=lat,
            longitude=lng,
            location_address=location["address"],
            location_city="Bogota",
            location_country="CO",
            city_id=bogota_city_id,
            incident_datetime=incident_dt,
            status=status,
            created_at=created_at,
            updated_at=created_at,
        )

        # Verified / rejected / disputed get a verifier and timestamp
        if status in (ReportStatus.VERIFIED, ReportStatus.REJECTED, ReportStatus.DISPUTED):
            verifier = random.choice(authority_analysts)
            report.verifier_id = verifier.id
            report.verified_at = created_at + timedelta(
                hours=random.randint(1, 48)
            )
            if status == ReportStatus.REJECTED:
                report.rejection_reason = random.choice([
                    "Evidencia insuficiente para confirmar la infraccion.",
                    "La placa no es legible en la evidencia proporcionada.",
                    "La imagen no corresponde a una infraccion de transito.",
                    "Duplicado de un reporte ya existente.",
                    "Ubicacion reportada no coincide con la evidencia.",
                ])

        session.add(report)
        reports.append(report)

        # Add 1-3 evidence items per report
        num_evidence = random.randint(1, 3)
        for ev_idx in range(num_evidence):
            evidence_n = (ev_idx % 5) + 1  # cycle through evidence_1..5
            evidence = Evidence(
                report_id=report.id,
                type=EvidenceType.IMAGE if random.random() < 0.85 else EvidenceType.VIDEO,
                url=f"{STORAGE_BASE}/sandbox/evidence/evidence_{evidence_n}.svg",
                thumbnail_url=f"{STORAGE_BASE}/sandbox/evidence/thumb_evidence_{evidence_n}.svg",
                mime_type="image/svg+xml" if random.random() < 0.85 else "video/mp4",
                file_size=random.randint(50_000, 5_000_000),
                created_at=created_at + timedelta(seconds=ev_idx),
            )
            session.add(evidence)
            evidence_count += 1

    await session.flush()
    logger.info(
        f"Created {len(reports)} reports with {evidence_count} evidence items"
    )
    return reports


async def seed_activities_and_tokens(
    session: AsyncSession,
    reports: list[Report],
    citizen_users: list[User],
) -> dict[str, Any]:
    """Create activity records and token transactions for verified reports.

    Returns summary stats.
    """
    # Fetch infraction reward data
    infraction_rows = (await session.execute(select(Infraction))).scalars().all()
    infraction_map = {inf.id: inf for inf in infraction_rows}

    total_multa = Decimal("0.000000")
    activities_created = 0
    tx_created = 0

    now = datetime.now(timezone.utc)

    for report in reports:
        infraction = infraction_map.get(report.infraction_id)
        if not infraction:
            continue

        # Every report gets a REPORT_SUBMITTED activity
        submit_activity = Activity(
            user_id=report.reporter_id,
            type=ActivityType.REPORT_SUBMITTED,
            points_earned=0,
            multa_earned=Decimal("0.000000"),
            reference_type="report",
            reference_id=str(report.id),
            created_at=report.created_at,
        )
        session.add(submit_activity)
        activities_created += 1

        if report.status == ReportStatus.VERIFIED:
            # REPORT_VERIFIED activity with rewards
            reward = infraction.multa_reward
            points = infraction.points_reward

            verified_activity = Activity(
                user_id=report.reporter_id,
                type=ActivityType.REPORT_VERIFIED,
                points_earned=points,
                multa_earned=reward,
                reference_type="report",
                reference_id=str(report.id),
                created_at=report.verified_at or report.created_at,
            )
            session.add(verified_activity)
            await session.flush()  # get the activity id
            activities_created += 1

            # Token transaction for the reward
            tx = TokenTransaction(
                user_id=report.reporter_id,
                type=TokenTxType.REWARD,
                amount=reward,
                status=TxStatus.CONFIRMED,
                activity_id=verified_activity.id,
                created_at=verified_activity.created_at,
                confirmed_at=verified_activity.created_at + timedelta(seconds=30),
            )
            session.add(tx)
            tx_created += 1
            total_multa += reward

    await session.flush()

    # Add a few staking positions for active citizens
    stakers = random.sample(citizen_users, min(4, len(citizen_users)))
    staking_created = 0
    for staker in stakers:
        stake_amount = Decimal(str(random.choice([10, 15, 20, 25, 30]))) + Decimal("0.000000")
        stake_dt = now - timedelta(days=random.randint(5, 25))
        position = StakingPosition(
            user_id=staker.id,
            amount=stake_amount,
            staked_at=stake_dt,
            unlock_at=stake_dt + timedelta(days=30),
            is_active=True,
        )
        session.add(position)

        # Matching STAKE token transaction
        stake_tx = TokenTransaction(
            user_id=staker.id,
            type=TokenTxType.STAKE,
            amount=stake_amount,
            status=TxStatus.CONFIRMED,
            created_at=stake_dt,
            confirmed_at=stake_dt + timedelta(seconds=15),
        )
        session.add(stake_tx)
        tx_created += 1
        staking_created += 1

    await session.flush()

    logger.info(
        f"Created {activities_created} activities, {tx_created} token txs, "
        f"{staking_created} staking positions | Total MULTA: {total_multa}"
    )
    return {
        "activities": activities_created,
        "token_transactions": tx_created,
        "staking_positions": staking_created,
        "total_multa": total_multa,
    }


async def seed_api_keys(
    session: AsyncSession,
    authority_admin: User,
    developer_user: User,
) -> list[dict[str, str]]:
    """Create 4 sandbox API keys (2 authority, 2 developer).

    Returns list of dicts with plaintext keys so they can be printed.
    """
    keys_info: list[dict[str, str]] = []

    key_specs = [
        {"name": "SMB Sandbox Key 1", "user": authority_admin, "scopes": ["reports:read", "reports:write", "analytics:read"]},
        {"name": "SMB Sandbox Key 2", "user": authority_admin, "scopes": ["reports:read", "analytics:read"]},
        {"name": "Developer Sandbox Key 1", "user": developer_user, "scopes": ["reports:read", "reports:write"]},
        {"name": "Developer Sandbox Key 2", "user": developer_user, "scopes": ["reports:read"]},
    ]

    for spec in key_specs:
        # Generate a realistic-looking API key
        raw_key = f"mlta_sandbox_{''.join(random.choices(string.ascii_lowercase + string.digits, k=32))}"
        key_hash = _sha256(raw_key)
        key_prefix = raw_key[:14]

        api_key = ApiKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=spec["name"],
            environment="sandbox",
            user_id=spec["user"].id,
            is_active=True,
            rate_limit=120,
            scopes=spec["scopes"],
        )
        session.add(api_key)
        keys_info.append({
            "name": spec["name"],
            "owner": spec["user"].display_name or spec["user"].email or "unknown",
            "key": raw_key,
            "prefix": key_prefix,
        })

    await session.flush()
    logger.info(f"Created {len(keys_info)} sandbox API keys")
    return keys_info


async def update_ledger_balances(
    session: AsyncSession, users: list[User]
) -> None:
    """Update hot wallet ledger balances based on confirmed reward transactions."""
    for user in users:
        result = await session.execute(
            select(TokenTransaction).where(
                TokenTransaction.user_id == user.id,
                TokenTransaction.type == TokenTxType.REWARD,
                TokenTransaction.status == TxStatus.CONFIRMED,
            )
        )
        txs = result.scalars().all()
        total = sum((tx.amount for tx in txs), Decimal("0.000000"))

        # Subtract staked amounts
        stake_result = await session.execute(
            select(StakingPosition).where(
                StakingPosition.user_id == user.id,
                StakingPosition.is_active == True,  # noqa: E712
            )
        )
        stakes = stake_result.scalars().all()
        staked = sum((s.amount for s in stakes), Decimal("0.000000"))

        balance = total - staked
        if balance < 0:
            balance = Decimal("0.000000")

        # Update ledger
        ledger_result = await session.execute(
            select(HotWalletLedger).where(HotWalletLedger.user_id == user.id)
        )
        ledger = ledger_result.scalar_one_or_none()
        if ledger:
            ledger.balance = balance

    await session.flush()
    logger.info("Updated hot wallet ledger balances")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def seed_test_data() -> None:
    """Run the full test data seed."""
    # Safety guard
    if settings.APP_ENV == "production":
        logger.error("ABORTED: Cannot seed test data in production (APP_ENV=production)!")
        return

    logger.info("=" * 60)
    logger.info("  Multando Sandbox Test Data Seeder")
    logger.info(f"  Environment: {settings.APP_ENV}")
    logger.info("=" * 60)

    async with async_session_maker() as session:
        try:
            # Idempotency check
            if await _check_already_seeded(session):
                logger.warning(
                    "Test data already exists (admin@sandbox.multando.dev found). "
                    "Skipping seed. Delete existing test data first if you want to re-seed."
                )
                return

            # Ensure Bogota city exists
            result = await session.execute(
                select(City).where(City.name == "Bogota", City.country_code == "CO")
            )
            bogota = result.scalar_one_or_none()
            if bogota is None:
                # Try with accent
                result = await session.execute(
                    select(City).where(
                        City.name.in_(["Bogota", "Bogotá"]),
                        City.country_code == "CO",
                    )
                )
                bogota = result.scalar_one_or_none()

            if bogota is None:
                logger.error(
                    "City 'Bogota' not found. Run city seed first: "
                    "python -m app.scripts.seed_cities"
                )
                return

            bogota_city_id: int = bogota.id

            # 1. Seed users
            users = await seed_users(session)
            admin_user = users[0]
            authority_admins = users[1:3]
            authority_analysts = users[3:6]
            authority_staff = users[1:6]
            citizen_users = users[6:]

            # 2. Custodial wallets
            await seed_custodial_wallets(session, users)

            # 3. Hot wallet ledger entries
            await seed_hot_wallet_ledger(session, users)

            # 4. Authority
            authority = await seed_authority(
                session, authority_staff, bogota_city_id
            )

            # 5. Webhooks
            await seed_webhooks(session, authority)

            # 6. Reports
            reports = await seed_reports(
                session,
                citizen_users,
                authority_analysts,
                bogota_city_id,
            )

            # 7. Activities & token transactions
            token_stats = await seed_activities_and_tokens(
                session, reports, citizen_users
            )

            # 8. API keys
            api_keys_info = await seed_api_keys(
                session,
                authority_admins[0],  # first authority admin
                citizen_users[0],     # first citizen as "developer"
            )

            # 9. Update ledger balances
            await update_ledger_balances(session, users)

            # Commit everything
            await session.commit()

            # Print summary
            verified_count = sum(
                1 for r in reports if r.status == ReportStatus.VERIFIED
            )
            pending_count = sum(
                1 for r in reports if r.status == ReportStatus.PENDING
            )
            rejected_count = sum(
                1 for r in reports if r.status == ReportStatus.REJECTED
            )
            disputed_count = sum(
                1 for r in reports if r.status == ReportStatus.DISPUTED
            )

            logger.info("")
            logger.info("=" * 60)
            logger.info("  SEED COMPLETED SUCCESSFULLY")
            logger.info("=" * 60)
            logger.info(f"  Users:              {len(users)}")
            logger.info(f"    Admin:            1")
            logger.info(f"    Authority staff:  {len(authority_staff)}")
            logger.info(f"    Citizens:         {len(citizen_users)}")
            logger.info(f"  Custodial wallets:  {len(users)}")
            logger.info(f"  Authority:          {authority.name}")
            logger.info(f"  Reports:            {len(reports)}")
            logger.info(f"    Pending:          {pending_count}")
            logger.info(f"    Verified:         {verified_count}")
            logger.info(f"    Rejected:         {rejected_count}")
            logger.info(f"    Disputed:         {disputed_count}")
            logger.info(f"  Activities:         {token_stats['activities']}")
            logger.info(f"  Token txs:          {token_stats['token_transactions']}")
            logger.info(f"  Staking positions:  {token_stats['staking_positions']}")
            logger.info(f"  Total MULTA:        {token_stats['total_multa']}")
            logger.info(f"  API keys:           {len(api_keys_info)}")
            logger.info("-" * 60)
            logger.info("  Test credentials:")
            logger.info(f"    Password (all):   {TEST_PASSWORD}")
            logger.info(f"    Admin email:      admin@{TEST_EMAIL_DOMAIN}")
            logger.info("-" * 60)
            logger.info("  Sandbox API keys:")
            for ki in api_keys_info:
                logger.info(f"    {ki['name']}:")
                logger.info(f"      Owner: {ki['owner']}")
                logger.info(f"      Key:   {ki['key']}")
            logger.info("=" * 60)

        except Exception as e:
            await session.rollback()
            logger.exception(f"Seed failed: {e}")
            raise


async def main() -> None:
    """Entry point."""
    await seed_test_data()


if __name__ == "__main__":
    asyncio.run(main())
