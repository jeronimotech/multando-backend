"""Create record_submissions table.

Tracks Multando report submissions to the Mintransporte RECORD form.
The model existed since earlier in the project but the migration was
never added, so sandbox and fresh databases are missing the table.

Revision ID: 011_record_submissions
Revises: 010_abuse_guard
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "011_record_submissions"
down_revision = "010_abuse_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use IF NOT EXISTS so environments that manually created the table
    # (or where a future migration recreates it) don't error out.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS record_submissions (
            id SERIAL PRIMARY KEY,
            report_id UUID NOT NULL UNIQUE
                REFERENCES reports(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            submitted_at TIMESTAMPTZ,
            error_message TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            response_data JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_record_submissions_report_id "
        "ON record_submissions (report_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_record_submissions_status "
        "ON record_submissions (status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS record_submissions")
