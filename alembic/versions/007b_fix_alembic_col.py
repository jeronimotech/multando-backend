"""Enlarge alembic_version column + normalize existing revision name.

Handles the case where the previous deployment wrote a revision name
longer than 32 characters and crashed halfway. This migration runs
BEFORE the rename of 008/009 takes effect.

Revision ID: 007b_fix_alembic
Revises: 007_add_evidence_capture_columns
"""

from alembic import op
import sqlalchemy as sa

revision = "007b_fix_alembic"
down_revision = "007_add_evidence_capture_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enlarge alembic_version column so future long names fit
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    # If a previous run left the DB at the long 008 name, normalize it
    op.execute(
        "UPDATE alembic_version SET version_num = '007b_fix_alembic' "
        "WHERE version_num IN ('008_add_report_statuses', '008_statuses')"
    )


def downgrade() -> None:
    pass
