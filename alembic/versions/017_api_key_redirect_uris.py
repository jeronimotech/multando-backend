"""Add redirect_uris column to api_keys for OAuth.

Revision ID: 017_api_key_redirect_uris
Revises: 016_oauth_codes
"""

from alembic import op

revision = "017_api_key_redirect_uris"
down_revision = "016_oauth_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS "
        "redirect_uris JSONB DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS redirect_uris")
