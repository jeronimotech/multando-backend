"""Abuse-prevention safeguards: penalty enum + user counters.

Adds:
    - ``false_report_penalty`` value to the ``activitytype`` Postgres enum
    - ``users.total_reports_count`` (int, default 0)
    - ``users.rejected_reports_count`` (int, default 0)

All operations are idempotent (``ADD COLUMN IF NOT EXISTS`` /
``ADD VALUE IF NOT EXISTS``) so the migration can safely be re-run.

Revision ID: 010_abuse_guard
Revises: 009_confidence_auth
"""

from alembic import op

revision = "010_abuse_guard"
down_revision = "009_confidence_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend the activitytype enum so we can write FALSE_REPORT_PENALTY
    # activity rows without a DB error.
    op.execute(
        "ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'false_report_penalty'"
    )

    # Per-user counters driving the rejection-rate warning flag.
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS total_reports_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS rejected_reports_count INTEGER NOT NULL DEFAULT 0"
    )

    # Backfill total_reports_count from existing reports so the ratio is
    # meaningful for pre-existing users. Rejected count stays at 0 —
    # we only care about authority rejections going forward and don't
    # want to retro-penalize users for community rejections under the
    # old flow.
    op.execute(
        """
        UPDATE users u
        SET total_reports_count = sub.cnt
        FROM (
            SELECT reporter_id, COUNT(*) AS cnt
            FROM reports
            GROUP BY reporter_id
        ) sub
        WHERE u.id = sub.reporter_id
          AND u.total_reports_count = 0;
        """
    )


def downgrade() -> None:
    # Postgres can't drop enum values cleanly; leave the value in place.
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS rejected_reports_count"
    )
    op.execute(
        "ALTER TABLE users DROP COLUMN IF EXISTS total_reports_count"
    )
