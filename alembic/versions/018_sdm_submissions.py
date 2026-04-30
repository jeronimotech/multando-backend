"""Create sdm_submissions table for Bogota SDM Google Form integration.

Revision ID: 018_sdm_submissions
Revises: 017_api_key_redirect_uris
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018_sdm_submissions"
down_revision = "017_api_key_redirect_uris"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sdm_submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("form_response_url", sa.String(length=500), nullable=True),
        sa.Column("prefill_url", sa.Text(), nullable=True),
        sa.Column("drive_evidence_links", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_sdm_submissions_report_id",
        "sdm_submissions",
        ["report_id"],
        unique=True,
    )
    op.create_index(
        "ix_sdm_submissions_status",
        "sdm_submissions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_sdm_submissions_status", table_name="sdm_submissions")
    op.drop_index("ix_sdm_submissions_report_id", table_name="sdm_submissions")
    op.drop_table("sdm_submissions")
