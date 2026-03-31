"""Add custodial wallet infrastructure.

Revision ID: 002
Revises: 001
Create Date: 2026-03-30

Adds:
- wallet_type column to users table (default: custodial)
- custodial_wallets table for encrypted keypair storage
- withdrawal_requests table for withdrawal tracking
- hot_wallet_ledger table for off-chain balance tracking
- WITHDRAWAL to token transaction type enum
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_custodial_wallets"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create wallet-related enums
    wallet_type_enum = postgresql.ENUM(
        "custodial", "self_custodial", name="wallettype", create_type=False
    )
    wallet_status_enum = postgresql.ENUM(
        "active", "frozen", "deactivated", name="walletstatus", create_type=False
    )
    withdrawal_status_enum = postgresql.ENUM(
        "pending_verification", "pending", "processing",
        "confirmed", "failed", "cancelled",
        name="withdrawalstatus", create_type=False,
    )

    # Create enums in database
    wallet_type_enum.create(op.get_bind(), checkfirst=True)
    wallet_status_enum.create(op.get_bind(), checkfirst=True)
    withdrawal_status_enum.create(op.get_bind(), checkfirst=True)

    # Add wallet_type to users
    op.add_column(
        "users",
        sa.Column(
            "wallet_type",
            wallet_type_enum,
            nullable=False,
            server_default="custodial",
        ),
    )

    # Add WITHDRAWAL to tokentxtype enum
    op.execute("ALTER TYPE tokentxtype ADD VALUE IF NOT EXISTS 'withdrawal'")

    # Create custodial_wallets table
    op.create_table(
        "custodial_wallets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_key", sa.String(100), nullable=False),
        sa.Column("encrypted_private_key", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_dek", sa.LargeBinary(), nullable=False),
        sa.Column("iv", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            wallet_status_enum,
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_tx_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("public_key"),
    )
    op.create_index("ix_custodial_wallets_user_id", "custodial_wallets", ["user_id"])
    op.create_index("ix_custodial_wallets_public_key", "custodial_wallets", ["public_key"])

    # Create withdrawal_requests table
    op.create_table(
        "withdrawal_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("destination_address", sa.String(100), nullable=False),
        sa.Column(
            "status",
            withdrawal_status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("tx_signature", sa.String(100), nullable=True, unique=True),
        sa.Column("fee_amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("verification_code", sa.String(10), nullable=True),
        sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_withdrawal_requests_user_id", "withdrawal_requests", ["user_id"])
    op.create_index("ix_withdrawal_requests_status", "withdrawal_requests", ["status"])

    # Create hot_wallet_ledger table
    op.create_table(
        "hot_wallet_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("balance", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_hot_wallet_ledger_user_id", "hot_wallet_ledger", ["user_id"])

    # Backfill: users with wallet_address → self_custodial
    op.execute(
        "UPDATE users SET wallet_type = 'self_custodial' WHERE wallet_address IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("hot_wallet_ledger")
    op.drop_table("withdrawal_requests")
    op.drop_table("custodial_wallets")
    op.drop_column("users", "wallet_type")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS withdrawalstatus")
    op.execute("DROP TYPE IF EXISTS walletstatus")
    op.execute("DROP TYPE IF EXISTS wallettype")
