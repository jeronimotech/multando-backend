"""Create federation tables for cross-instance data sharing.

Adds federated_reports and federation_instances tables to support
self-hosted instances pushing anonymized data to the central hub.

Revision ID: 014_federation
Revises: 013_api_keys_environment
"""

import sqlalchemy as sa
from alembic import op

revision = "014_federation"
down_revision = "013_api_keys_environment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Federation instances table --
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS federation_instances (
            id SERIAL PRIMARY KEY,
            instance_id VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            api_key_hash VARCHAR(64) NOT NULL,
            city VARCHAR(200),
            country VARCHAR(5) DEFAULT 'CO',
            is_active BOOLEAN DEFAULT TRUE,
            last_sync_at TIMESTAMPTZ,
            total_reports_synced INTEGER DEFAULT 0,
            registered_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federation_instances_instance_id "
        "ON federation_instances (instance_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federation_instances_is_active "
        "ON federation_instances (is_active)"
    )

    # -- Federated reports table --
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS federated_reports (
            id SERIAL PRIMARY KEY,
            instance_id VARCHAR(50) NOT NULL,
            instance_name VARCHAR(200),
            report_short_id VARCHAR(20) NOT NULL,
            infraction_code VARCHAR(50),
            infraction_name VARCHAR(200),
            vehicle_category VARCHAR(50),
            city_name VARCHAR(200),
            country_code VARCHAR(5) DEFAULT 'CO',
            status VARCHAR(20) NOT NULL,
            reported_at TIMESTAMPTZ NOT NULL,
            latitude_approx NUMERIC(8, 4),
            longitude_approx NUMERIC(8, 4),
            synced_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federated_reports_instance_id "
        "ON federated_reports (instance_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federated_reports_synced_at "
        "ON federated_reports (synced_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federated_reports_status "
        "ON federated_reports (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federated_reports_instance_short_id "
        "ON federated_reports (instance_id, report_short_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS federated_reports")
    op.execute("DROP TABLE IF EXISTS federation_instances")
