"""Create partners, partner_offers, and offer_redemptions tables.

Adds the partnership/sponsorship system allowing local businesses to
offer discounts and experiences redeemable with MULTA tokens.

Revision ID: 012_partnerships
Revises: 011_record_submissions
"""

import sqlalchemy as sa
from alembic import op

revision = "012_partnerships"
down_revision = "011_record_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Add new enum value to activitytype --
    op.execute(
        "ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'offer_redeemed'"
    )

    # -- Partners table --
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS partners (
            id SERIAL PRIMARY KEY,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            name VARCHAR(200) NOT NULL,
            slug VARCHAR(200) NOT NULL UNIQUE,
            description TEXT,
            logo_url VARCHAR(500),
            cover_image_url VARCHAR(500),
            website_url VARCHAR(500),
            contact_email VARCHAR(255),
            contact_phone VARCHAR(20),
            category VARCHAR(20) NOT NULL DEFAULT 'other',
            tier VARCHAR(20) NOT NULL DEFAULT 'community',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            address VARCHAR(500),
            city_id INTEGER REFERENCES cities(id) ON DELETE SET NULL,
            latitude NUMERIC(10, 7),
            longitude NUMERIC(10, 7),
            partner_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_partners_slug ON partners (slug)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_partners_status ON partners (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_partners_user_id ON partners (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_partners_category ON partners (category)"
    )

    # -- Partner offers table --
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS partner_offers (
            id SERIAL PRIMARY KEY,
            partner_id INTEGER NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
            title VARCHAR(300) NOT NULL,
            description VARCHAR(1000),
            offer_type VARCHAR(30) NOT NULL,
            discount_value NUMERIC(10, 2),
            multa_cost NUMERIC(18, 6) NOT NULL,
            original_price NUMERIC(10, 2),
            image_url VARCHAR(500),
            quantity_total INTEGER,
            quantity_remaining INTEGER,
            valid_from TIMESTAMPTZ,
            valid_until TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_featured BOOLEAN NOT NULL DEFAULT FALSE,
            terms TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_partner_offers_partner_id "
        "ON partner_offers (partner_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_partner_offers_is_active "
        "ON partner_offers (is_active)"
    )

    # -- Offer redemptions table --
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS offer_redemptions (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            offer_id INTEGER NOT NULL REFERENCES partner_offers(id) ON DELETE CASCADE,
            redemption_code VARCHAR(20) NOT NULL UNIQUE,
            qr_data VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            multa_amount NUMERIC(18, 6) NOT NULL,
            redeemed_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offer_redemptions_user_id "
        "ON offer_redemptions (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offer_redemptions_offer_id "
        "ON offer_redemptions (offer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offer_redemptions_code "
        "ON offer_redemptions (redemption_code)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_offer_redemptions_status "
        "ON offer_redemptions (status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS offer_redemptions")
    op.execute("DROP TABLE IF EXISTS partner_offers")
    op.execute("DROP TABLE IF EXISTS partners")
    # Note: ALTER TYPE ... DROP VALUE is not supported in PostgreSQL;
    # the 'offer_redeemed' enum value will remain harmlessly.
