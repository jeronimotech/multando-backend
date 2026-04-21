"""Create oauth_authorization_codes table for OAuth 2.0 provider flow.

Revision ID: 016_oauth_codes
Revises: 015_social_auth
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "016_oauth_codes"
down_revision = "015_social_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("scope", sa.String(500), nullable=False),
        sa.Column("state", sa.String(200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "used", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauth_authorization_codes_code",
        "oauth_authorization_codes",
        ["code"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_authorization_codes_user_id",
        "oauth_authorization_codes",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_authorization_codes_user_id",
        table_name="oauth_authorization_codes",
    )
    op.drop_index(
        "ix_oauth_authorization_codes_code",
        table_name="oauth_authorization_codes",
    )
    op.drop_table("oauth_authorization_codes")
