"""Fix remaining enum values from UPPERCASE to lowercase.

Migration 005 missed vehiclecategory and activitytype.

Revision ID: 006_fix_remaining_enum_values
Revises: 005_fix_enum_values_lowercase
"""

from alembic import op

revision = "006_fix_remaining_enum_values"
down_revision = "005_fix_enum_values_lowercase"
branch_labels = None
depends_on = None

ENUM_RENAMES = [
    ("vehiclecategory", [
        ("PRIVATE", "private"),
        ("PUBLIC", "public"),
        ("DIPLOMATIC", "diplomatic"),
        ("EMERGENCY", "emergency"),
        ("COMMERCIAL", "commercial"),
    ]),
    ("activitytype", [
        ("REPORT_SUBMITTED", "report_submitted"),
        ("REPORT_VERIFIED", "report_verified"),
        ("VERIFICATION_DONE", "verification_done"),
        ("DAILY_LOGIN", "daily_login"),
        ("REFERRAL", "referral"),
        ("LEVEL_UP", "level_up"),
        ("BADGE_EARNED", "badge_earned"),
    ]),
]


def upgrade() -> None:
    for enum_name, renames in ENUM_RENAMES:
        for old_val, new_val in renames:
            op.execute(
                f"ALTER TYPE {enum_name} RENAME VALUE '{old_val}' TO '{new_val}'"
            )


def downgrade() -> None:
    for enum_name, renames in ENUM_RENAMES:
        for old_val, new_val in renames:
            op.execute(
                f"ALTER TYPE {enum_name} RENAME VALUE '{new_val}' TO '{old_val}'"
            )
