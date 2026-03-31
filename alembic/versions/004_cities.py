"""Add cities table and city_id FK to authorities and reports.

Revision ID: 004_cities
Revises: 003_api_keys
Create Date: 2026-03-30

Adds:
- cities table for structured city-based multi-tenancy
- city_id FK on authorities table
- city_id FK on reports table
- Seeds initial Colombian cities
"""

from alembic import op
import sqlalchemy as sa

revision = "004_cities"
down_revision = "003_api_keys"
branch_labels = None
depends_on = None

# Colombian cities seed data
COLOMBIAN_CITIES = [
    ("Bogotá", "CO", "Cundinamarca", 4.6097, -74.0817, "America/Bogota"),
    ("Medellín", "CO", "Antioquia", 6.2442, -75.5812, "America/Bogota"),
    ("Cali", "CO", "Valle del Cauca", 3.4516, -76.5320, "America/Bogota"),
    ("Barranquilla", "CO", "Atlántico", 10.9685, -74.7813, "America/Bogota"),
    ("Cartagena", "CO", "Bolívar", 10.3910, -75.5144, "America/Bogota"),
    ("Bucaramanga", "CO", "Santander", 7.1254, -73.1198, "America/Bogota"),
    ("Cúcuta", "CO", "Norte de Santander", 7.8939, -72.5078, "America/Bogota"),
    ("Pereira", "CO", "Risaralda", 4.8133, -75.6961, "America/Bogota"),
    ("Santa Marta", "CO", "Magdalena", 11.2408, -74.1990, "America/Bogota"),
    ("Manizales", "CO", "Caldas", 5.0689, -75.5174, "America/Bogota"),
]


def upgrade() -> None:
    # Create cities table
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("state_province", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "country_code", name="uq_city_name_country"),
    )
    op.create_index("ix_cities_name", "cities", ["name"])
    op.create_index("ix_cities_country_code", "cities", ["country_code"])

    # Add city_id FK to authorities
    op.add_column(
        "authorities",
        sa.Column("city_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_authorities_city_id",
        "authorities",
        "cities",
        ["city_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_authorities_city_id", "authorities", ["city_id"])

    # Add city_id FK to reports
    op.add_column(
        "reports",
        sa.Column("city_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_reports_city_id",
        "reports",
        "cities",
        ["city_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_reports_city_id", "reports", ["city_id"])

    # Seed Colombian cities
    cities_table = sa.table(
        "cities",
        sa.column("name", sa.String),
        sa.column("country_code", sa.String),
        sa.column("state_province", sa.String),
        sa.column("latitude", sa.Float),
        sa.column("longitude", sa.Float),
        sa.column("timezone", sa.String),
    )
    op.bulk_insert(
        cities_table,
        [
            {
                "name": name,
                "country_code": cc,
                "state_province": sp,
                "latitude": lat,
                "longitude": lon,
                "timezone": tz,
            }
            for name, cc, sp, lat, lon, tz in COLOMBIAN_CITIES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_reports_city_id", table_name="reports")
    op.drop_constraint("fk_reports_city_id", "reports", type_="foreignkey")
    op.drop_column("reports", "city_id")

    op.drop_index("ix_authorities_city_id", table_name="authorities")
    op.drop_constraint("fk_authorities_city_id", "authorities", type_="foreignkey")
    op.drop_column("authorities", "city_id")

    op.drop_index("ix_cities_country_code", table_name="cities")
    op.drop_index("ix_cities_name", table_name="cities")
    op.drop_table("cities")
