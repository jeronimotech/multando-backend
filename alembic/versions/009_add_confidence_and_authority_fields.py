"""Add confidence scoring and authority validation columns to reports.

Adds:
    - confidence_score (int, default 50)
    - confidence_factors (jsonb)
    - verification_count (int, default 0)
    - rejection_count (int, default 0)
    - authority_validator_id (uuid, FK users.id)
    - authority_validated_at (timestamptz)
    - authority_notes (text)

Revision ID: 009_add_confidence_and_authority_fields
Revises: 008_add_report_statuses
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "009_add_confidence_and_authority_fields"
down_revision = "008_add_report_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Confidence scoring
    op.add_column(
        "reports",
        sa.Column(
            "confidence_score",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
    )
    op.add_column(
        "reports",
        sa.Column("confidence_factors", JSONB, nullable=True),
    )

    # Community voting counters
    op.add_column(
        "reports",
        sa.Column(
            "verification_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "rejection_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # Authority validation fields
    op.add_column(
        "reports",
        sa.Column(
            "authority_validator_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "reports",
        sa.Column(
            "authority_validated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "reports",
        sa.Column("authority_notes", sa.Text(), nullable=True),
    )

    # Helpful index for queue lookups ordered by confidence desc
    op.create_index(
        "ix_reports_status_confidence",
        "reports",
        ["status", "confidence_score"],
    )

    # Backfill confidence_score for existing reports using a lightweight
    # heuristic so the authority review queue isn't uniformly 50/100.
    # Rules (see ConfidenceScorer for the canonical implementation):
    #   +30 if any evidence has capture_verified
    #   +10 if any evidence is an image
    #   +10 if GPS is inside Colombia
    #   +10 if the plate matches the Colombian format
    #   final score clamped to [0, 100]
    op.execute(
        """
        UPDATE reports r
        SET confidence_score = LEAST(100, GREATEST(0,
            50
            + CASE WHEN EXISTS (
                SELECT 1 FROM evidences e
                WHERE e.report_id = r.id AND e.capture_verified = true
              ) THEN 30 ELSE 0 END
            + CASE WHEN EXISTS (
                SELECT 1 FROM evidences e
                WHERE e.report_id = r.id AND e.type = 'image'
              ) THEN 10 ELSE 0 END
            + CASE WHEN r.latitude > -5 AND r.latitude < 13
                   AND r.longitude > -82 AND r.longitude < -66
              THEN 10 ELSE 0 END
            + CASE WHEN r.vehicle_plate IS NOT NULL
                   AND regexp_replace(upper(r.vehicle_plate), '[- ]', '', 'g')
                       ~ '^[A-Z]{3}[0-9]{2,4}[A-Z]?$'
              THEN 10 ELSE 0 END
        ));
        """
    )


def downgrade() -> None:
    op.drop_index("ix_reports_status_confidence", table_name="reports")
    op.drop_column("reports", "authority_notes")
    op.drop_column("reports", "authority_validated_at")
    op.drop_column("reports", "authority_validator_id")
    op.drop_column("reports", "rejection_count")
    op.drop_column("reports", "verification_count")
    op.drop_column("reports", "confidence_factors")
    op.drop_column("reports", "confidence_score")
