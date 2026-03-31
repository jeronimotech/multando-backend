"""Fix enum values from UPPERCASE to lowercase.

The initial migration created PostgreSQL enums with UPPERCASE labels
(e.g. 'CITIZEN') but SQLAlchemy sends lowercase .value (e.g. 'citizen').

Revision ID: 005
Revises: 004
"""

from alembic import op

revision = "005_fix_enum_values_lowercase"
down_revision = "004_cities"
branch_labels = None
depends_on = None

# Map: (enum_type_name, [(old_uppercase, new_lowercase), ...])
ENUM_RENAMES = [
    ("userrole", [
        ("CITIZEN", "citizen"),
        ("AUTHORITY", "authority"),
        ("ADMIN", "admin"),
    ]),
    ("badgerarity", [
        ("COMMON", "common"),
        ("RARE", "rare"),
        ("EPIC", "epic"),
        ("LEGENDARY", "legendary"),
    ]),
    ("infractioncategory", [
        ("SPEED", "speed"),
        ("SAFETY", "safety"),
        ("PARKING", "parking"),
        ("BEHAVIOR", "behavior"),
    ]),
    ("infractionseverity", [
        ("LOW", "low"),
        ("MEDIUM", "medium"),
        ("HIGH", "high"),
        ("CRITICAL", "critical"),
    ]),
    ("reportsource", [
        ("WEB", "web"),
        ("MOBILE", "mobile"),
        ("WHATSAPP", "whatsapp"),
        # 'sdk' added separately below
    ]),
    ("reportstatus", [
        ("PENDING", "pending"),
        ("VERIFIED", "verified"),
        ("REJECTED", "rejected"),
        ("DISPUTED", "disputed"),
    ]),
    ("evidencetype", [
        ("IMAGE", "image"),
        ("VIDEO", "video"),
    ]),
    ("tokentxtype", [
        ("REWARD", "reward"),
        ("STAKE", "stake"),
        ("UNSTAKE", "unstake"),
        ("TRANSFER", "transfer"),
        ("BURN", "burn"),
    ]),
    ("txstatus", [
        ("PENDING", "pending"),
        ("CONFIRMED", "confirmed"),
        ("FAILED", "failed"),
    ]),
    ("conversationstatus", [
        ("ACTIVE", "active"),
        ("COMPLETED", "completed"),
        ("ABANDONED", "abandoned"),
    ]),
    ("messagedirection", [
        ("INBOUND", "inbound"),
        ("OUTBOUND", "outbound"),
    ]),
    ("messagetype", [
        ("TEXT", "text"),
        ("IMAGE", "image"),
        ("VIDEO", "video"),
        ("LOCATION", "location"),
        ("BUTTON", "button"),
        ("LIST", "list"),
    ]),
    ("subscriptiontier", [
        ("FREE", "free"),
        ("BASIC", "basic"),
        ("PREMIUM", "premium"),
        ("ENTERPRISE", "enterprise"),
    ]),
    ("authorityrole", [
        ("VIEWER", "viewer"),
        ("ANALYST", "analyst"),
        ("ADMIN", "admin"),
    ]),
]


def upgrade() -> None:
    for enum_name, renames in ENUM_RENAMES:
        for old_val, new_val in renames:
            op.execute(
                f"ALTER TYPE {enum_name} RENAME VALUE '{old_val}' TO '{new_val}'"
            )

    # Add missing enum values that were added after initial migration
    op.execute("ALTER TYPE reportsource ADD VALUE IF NOT EXISTS 'sdk'")
    op.execute("ALTER TYPE badgerarity ADD VALUE IF NOT EXISTS 'uncommon'")
    op.execute("ALTER TYPE tokentxtype ADD VALUE IF NOT EXISTS 'withdrawal'")


def downgrade() -> None:
    for enum_name, renames in ENUM_RENAMES:
        for old_val, new_val in renames:
            op.execute(
                f"ALTER TYPE {enum_name} RENAME VALUE '{new_val}' TO '{old_val}'"
            )
