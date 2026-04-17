"""Add environment column to api_keys table.

The model has an `environment` column (sandbox/production) but the
original migration 003 didn't include it.

Revision ID: 013_api_keys_environment
Revises: 012_partnerships
"""

from alembic import op

revision = "013_api_keys_environment"
down_revision = "012_partnerships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS "
        "environment VARCHAR(20) NOT NULL DEFAULT 'production'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS environment")
