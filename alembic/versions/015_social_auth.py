"""Add social auth columns to users table.

Adds auth_provider and provider_id columns to support Google/GitHub
OAuth login alongside the existing email+password flow.

Revision ID: 015_social_auth
Revises: 014_federation
"""

import sqlalchemy as sa
from alembic import op

revision = "015_social_auth"
down_revision = "014_federation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "auth_provider VARCHAR(20) NOT NULL DEFAULT 'email'"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "provider_id VARCHAR(255)"
    )
    # Partial unique index: only enforce uniqueness where provider_id is set
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_provider_id "
        "ON users (provider_id) WHERE provider_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_provider_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS provider_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS auth_provider")
