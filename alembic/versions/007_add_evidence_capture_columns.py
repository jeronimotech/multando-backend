"""Add secure capture columns to evidences table.

Revision ID: 007_add_evidence_capture_columns
Revises: 006_fix_remaining_enum_values
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "007_add_evidence_capture_columns"
down_revision = "006_fix_remaining_enum_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidences", sa.Column("capture_verified", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("evidences", sa.Column("image_hash", sa.String(128), nullable=True))
    op.add_column("evidences", sa.Column("capture_signature", sa.String(512), nullable=True))
    op.add_column("evidences", sa.Column("capture_metadata", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("evidences", "capture_metadata")
    op.drop_column("evidences", "capture_signature")
    op.drop_column("evidences", "image_hash")
    op.drop_column("evidences", "capture_verified")
