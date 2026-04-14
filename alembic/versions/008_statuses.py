"""Add new report statuses for authority validation workflow.

Adds ``community_verified``, ``authority_review`` and ``approved`` to the
``reportstatus`` Postgres enum. Existing values (``pending``, ``verified``,
``rejected``, ``disputed``) are preserved. ``verified`` remains in the enum
for legacy/backward-compat but new flows should no longer set it.

Revision ID: 008_statuses
Revises: 007_add_evidence_capture_columns
"""

from alembic import op

revision = "008_statuses"
down_revision = "007b_fix_alembic"
branch_labels = None
depends_on = None


NEW_VALUES = ("community_verified", "authority_review", "approved")


def upgrade() -> None:
    # ``ADD VALUE IF NOT EXISTS`` makes the migration idempotent. In
    # PostgreSQL 12+ it can safely run inside a transaction block.
    for value in NEW_VALUES:
        op.execute(
            f"ALTER TYPE reportstatus ADD VALUE IF NOT EXISTS '{value}'"
        )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values cleanly; downgrade
    # is intentionally a no-op to avoid destructive operations.
    pass
