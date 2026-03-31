"""Initial database schema for Multando.

Revision ID: 001_initial_schema
Revises:
Create Date: 2024-01-15 00:00:00.000000

Creates all tables for the Multando application:
- users, levels, badges, user_badges (user management & gamification)
- reports, evidences, infractions, vehicle_types (traffic reporting)
- activities, token_transactions, staking_positions (blockchain & rewards)
- conversations, messages (WhatsApp bot)
- authorities, authority_users (authority management)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables."""

    # ============================================================
    # LEVELS table - gamification tiers
    # ============================================================
    op.create_table(
        "levels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("title_en", sa.String(length=100), nullable=False),
        sa.Column("title_es", sa.String(length=100), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column("min_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column(
            "multa_bonus",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tier"),
    )
    op.create_index(op.f("ix_levels_tier"), "levels", ["tier"], unique=True)

    # ============================================================
    # BADGES table - achievement badges
    # ============================================================
    op.create_table(
        "badges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=False),
        sa.Column("name_es", sa.String(length=100), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column(
            "rarity",
            sa.Enum("COMMON", "RARE", "EPIC", "LEGENDARY", name="badgerarity"),
            nullable=False,
            server_default="COMMON",
        ),
        sa.Column(
            "multa_reward",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_nft", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("nft_metadata_uri", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_badges_code"), "badges", ["code"], unique=True)

    # ============================================================
    # USERS table - main user entity
    # ============================================================
    op.create_table(
        "users",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("username", sa.String(length=50), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("wallet_address", sa.String(length=100), nullable=True),
        # Profile
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=False, server_default="es"),
        # Gamification
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("level_id", sa.Integer(), nullable=True),
        sa.Column(
            "reputation_score",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="100.00",
        ),
        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "role",
            sa.Enum("CITIZEN", "AUTHORITY", "ADMIN", name="userrole"),
            nullable=False,
            server_default="CITIZEN",
        ),
        # Timestamps
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["level_id"], ["levels.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("phone_number"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("wallet_address"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_phone_number"), "users", ["phone_number"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)
    op.create_index(op.f("ix_users_wallet_address"), "users", ["wallet_address"], unique=True)

    # ============================================================
    # USER_BADGES table - user-badge association
    # ============================================================
    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("badge_id", sa.Integer(), nullable=False),
        sa.Column(
            "awarded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("nft_mint_address", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["badge_id"], ["badges.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )
    op.create_index(op.f("ix_user_badges_user_id"), "user_badges", ["user_id"])
    op.create_index(op.f("ix_user_badges_badge_id"), "user_badges", ["badge_id"])

    # ============================================================
    # INFRACTIONS table - types of traffic violations
    # ============================================================
    op.create_table(
        "infractions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_en", sa.String(length=200), nullable=False),
        sa.Column("name_es", sa.String(length=200), nullable=False),
        sa.Column("description_en", sa.Text(), nullable=True),
        sa.Column("description_es", sa.Text(), nullable=True),
        sa.Column(
            "category",
            sa.Enum("SPEED", "SAFETY", "PARKING", "BEHAVIOR", name="infractioncategory"),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="infractionseverity"),
            nullable=False,
            server_default="MEDIUM",
        ),
        sa.Column("points_reward", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "multa_reward",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="1.000000",
        ),
        sa.Column("icon", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_infractions_code"), "infractions", ["code"], unique=True)
    op.create_index(op.f("ix_infractions_category"), "infractions", ["category"])
    op.create_index(op.f("ix_infractions_is_active"), "infractions", ["is_active"])

    # ============================================================
    # VEHICLE_TYPES table - types of vehicles
    # ============================================================
    op.create_table(
        "vehicle_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=False),
        sa.Column("name_es", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=100), nullable=True),
        sa.Column("plate_pattern", sa.String(length=100), nullable=True),
        sa.Column("requires_plate", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_vehicle_types_code"), "vehicle_types", ["code"], unique=True)

    # ============================================================
    # REPORTS table - traffic violation reports
    # ============================================================
    op.create_table(
        "reports",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("short_id", sa.String(length=12), nullable=False),
        # Reporter
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum("WEB", "MOBILE", "WHATSAPP", name="reportsource"),
            nullable=False,
            server_default="MOBILE",
        ),
        # Infraction details
        sa.Column("infraction_id", sa.Integer(), nullable=False),
        # Vehicle details
        sa.Column("vehicle_plate", sa.String(length=20), nullable=True),
        sa.Column("vehicle_type_id", sa.Integer(), nullable=True),
        sa.Column(
            "vehicle_category",
            sa.Enum(
                "PRIVATE", "PUBLIC", "DIPLOMATIC", "EMERGENCY", "COMMERCIAL",
                name="vehiclecategory"
            ),
            nullable=False,
            server_default="PRIVATE",
        ),
        # Location
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("location_address", sa.String(length=500), nullable=True),
        sa.Column("location_city", sa.String(length=100), nullable=True),
        sa.Column("location_country", sa.String(length=2), nullable=False, server_default="DO"),
        # Incident timing
        sa.Column("incident_datetime", sa.DateTime(timezone=True), nullable=False),
        # Verification status
        sa.Column(
            "status",
            sa.Enum("PENDING", "VERIFIED", "REJECTED", "DISPUTED", name="reportstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("verifier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        # Blockchain
        sa.Column("on_chain", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("tx_signature", sa.String(length=100), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["infraction_id"], ["infractions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_type_id"], ["vehicle_types.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["verifier_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_id"),
    )
    op.create_index(op.f("ix_reports_short_id"), "reports", ["short_id"], unique=True)
    op.create_index(op.f("ix_reports_reporter_id"), "reports", ["reporter_id"])
    op.create_index(op.f("ix_reports_status"), "reports", ["status"])
    op.create_index(op.f("ix_reports_vehicle_plate"), "reports", ["vehicle_plate"])
    op.create_index(op.f("ix_reports_created_at"), "reports", ["created_at"])
    op.create_index(op.f("ix_reports_location_city"), "reports", ["location_city"])

    # ============================================================
    # EVIDENCES table - evidence files for reports
    # ============================================================
    op.create_table(
        "evidences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            sa.Enum("IMAGE", "VIDEO", name="evidencetype"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("ipfs_hash", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_evidences_report_id"), "evidences", ["report_id"])

    # ============================================================
    # ACTIVITIES table - user activity log
    # ============================================================
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "REPORT_SUBMITTED",
                "REPORT_VERIFIED",
                "VERIFICATION_DONE",
                "DAILY_LOGIN",
                "REFERRAL",
                "LEVEL_UP",
                "BADGE_EARNED",
                name="activitytype",
            ),
            nullable=False,
        ),
        sa.Column("points_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "multa_earned",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column("reference_type", sa.String(length=50), nullable=True),
        sa.Column("reference_id", sa.String(length=100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_activities_user_id"), "activities", ["user_id"])
    op.create_index(op.f("ix_activities_type"), "activities", ["type"])
    op.create_index(op.f("ix_activities_created_at"), "activities", ["created_at"])

    # ============================================================
    # TOKEN_TRANSACTIONS table - blockchain transactions
    # ============================================================
    op.create_table(
        "token_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "type",
            sa.Enum("REWARD", "STAKE", "UNSTAKE", "TRANSFER", "BURN", name="tokentxtype"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("tx_signature", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PENDING", "CONFIRMED", "FAILED", name="txstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("activity_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tx_signature"),
    )
    op.create_index(op.f("ix_token_transactions_user_id"), "token_transactions", ["user_id"])
    op.create_index(op.f("ix_token_transactions_type"), "token_transactions", ["type"])
    op.create_index(op.f("ix_token_transactions_status"), "token_transactions", ["status"])
    op.create_index(
        op.f("ix_token_transactions_tx_signature"),
        "token_transactions",
        ["tx_signature"],
        unique=True,
    )

    # ============================================================
    # STAKING_POSITIONS table - MULTA staking
    # ============================================================
    op.create_table(
        "staking_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column(
            "staked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("unlock_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "rewards_claimed",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="0.000000",
        ),
        sa.Column("last_claim_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_staking_positions_user_id"), "staking_positions", ["user_id"])
    op.create_index(op.f("ix_staking_positions_is_active"), "staking_positions", ["is_active"])

    # ============================================================
    # CONVERSATIONS table - WhatsApp conversations
    # ============================================================
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "COMPLETED", "ABANDONED", name="conversationstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("draft_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_phone_number"), "conversations", ["phone_number"])
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"])
    op.create_index(op.f("ix_conversations_status"), "conversations", ["status"])

    # ============================================================
    # MESSAGES table - WhatsApp messages
    # ============================================================
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("INBOUND", "OUTBOUND", name="messagedirection"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "message_type",
            sa.Enum("TEXT", "IMAGE", "VIDEO", "LOCATION", "BUTTON", "LIST", name="messagetype"),
            nullable=False,
            server_default="TEXT",
        ),
        sa.Column("whatsapp_message_id", sa.String(length=100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_conversation_id"), "messages", ["conversation_id"])
    op.create_index(op.f("ix_messages_whatsapp_message_id"), "messages", ["whatsapp_message_id"])
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"])

    # ============================================================
    # AUTHORITIES table - government authorities
    # ============================================================
    op.create_table(
        "authorities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False, server_default="DO"),
        sa.Column("city", sa.String(length=100), nullable=True),
        # Subscription
        sa.Column(
            "subscription_tier",
            sa.Enum("FREE", "BASIC", "PREMIUM", "ENTERPRISE", name="subscriptiontier"),
            nullable=False,
            server_default="FREE",
        ),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
        # API access
        sa.Column("api_key_hash", sa.String(length=255), nullable=True),
        sa.Column("rate_limit", sa.Integer(), nullable=False, server_default="1000"),
        # Contact
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_authorities_code"), "authorities", ["code"], unique=True)
    op.create_index(op.f("ix_authorities_country"), "authorities", ["country"])

    # ============================================================
    # AUTHORITY_USERS table - authority user association
    # ============================================================
    op.create_table(
        "authority_users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("authority_id", sa.Integer(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum("VIEWER", "ANALYST", "ADMIN", name="authorityrole"),
            nullable=False,
            server_default="VIEWER",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["authority_id"], ["authorities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("authority_id", "user_id", name="uq_authority_user"),
    )
    op.create_index(op.f("ix_authority_users_authority_id"), "authority_users", ["authority_id"])
    op.create_index(op.f("ix_authority_users_user_id"), "authority_users", ["user_id"])


def downgrade() -> None:
    """Drop all tables in reverse order."""

    # Drop association/dependent tables first
    op.drop_index(op.f("ix_authority_users_user_id"), table_name="authority_users")
    op.drop_index(op.f("ix_authority_users_authority_id"), table_name="authority_users")
    op.drop_table("authority_users")

    op.drop_index(op.f("ix_authorities_country"), table_name="authorities")
    op.drop_index(op.f("ix_authorities_code"), table_name="authorities")
    op.drop_table("authorities")

    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_index(op.f("ix_messages_whatsapp_message_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_conversations_status"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_phone_number"), table_name="conversations")
    op.drop_table("conversations")

    op.drop_index(op.f("ix_staking_positions_is_active"), table_name="staking_positions")
    op.drop_index(op.f("ix_staking_positions_user_id"), table_name="staking_positions")
    op.drop_table("staking_positions")

    op.drop_index(op.f("ix_token_transactions_tx_signature"), table_name="token_transactions")
    op.drop_index(op.f("ix_token_transactions_status"), table_name="token_transactions")
    op.drop_index(op.f("ix_token_transactions_type"), table_name="token_transactions")
    op.drop_index(op.f("ix_token_transactions_user_id"), table_name="token_transactions")
    op.drop_table("token_transactions")

    op.drop_index(op.f("ix_activities_created_at"), table_name="activities")
    op.drop_index(op.f("ix_activities_type"), table_name="activities")
    op.drop_index(op.f("ix_activities_user_id"), table_name="activities")
    op.drop_table("activities")

    op.drop_index(op.f("ix_evidences_report_id"), table_name="evidences")
    op.drop_table("evidences")

    op.drop_index(op.f("ix_reports_location_city"), table_name="reports")
    op.drop_index(op.f("ix_reports_created_at"), table_name="reports")
    op.drop_index(op.f("ix_reports_vehicle_plate"), table_name="reports")
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_reporter_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_short_id"), table_name="reports")
    op.drop_table("reports")

    op.drop_index(op.f("ix_vehicle_types_code"), table_name="vehicle_types")
    op.drop_table("vehicle_types")

    op.drop_index(op.f("ix_infractions_is_active"), table_name="infractions")
    op.drop_index(op.f("ix_infractions_category"), table_name="infractions")
    op.drop_index(op.f("ix_infractions_code"), table_name="infractions")
    op.drop_table("infractions")

    op.drop_index(op.f("ix_user_badges_badge_id"), table_name="user_badges")
    op.drop_index(op.f("ix_user_badges_user_id"), table_name="user_badges")
    op.drop_table("user_badges")

    op.drop_index(op.f("ix_users_wallet_address"), table_name="users")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_phone_number"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_badges_code"), table_name="badges")
    op.drop_table("badges")

    op.drop_index(op.f("ix_levels_tier"), table_name="levels")
    op.drop_table("levels")

    # Drop enums
    sa.Enum(name="authorityrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="subscriptiontier").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="messagetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="messagedirection").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="conversationstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="txstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tokentxtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="activitytype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reportstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="vehiclecategory").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reportsource").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="evidencetype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="infractionseverity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="infractioncategory").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="badgerarity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
