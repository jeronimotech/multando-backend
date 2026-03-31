"""Alembic environment configuration for async SQLAlchemy with asyncpg."""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models to ensure they are registered with Base.metadata
# This is required for autogenerate support
from app.models import (
    # Base and mixins
    Base,
    # User models
    User,
    Level,
    Badge,
    UserBadge,
    # Report models
    Report,
    Evidence,
    Infraction,
    VehicleType,
    # Activity models
    Activity,
    TokenTransaction,
    StakingPosition,
    # Conversation models
    Conversation,
    Message,
    # Authority models
    Authority,
    AuthorityUser,
)
from app.core.config import settings

# this is the Alembic Config object
config = context.config

# Get DATABASE_URL from environment variable or settings
# Priority: Environment variable > settings
database_url = os.environ.get("DATABASE_URL", settings.database_url_sync)

# Ensure we use the sync driver (psycopg2) for Alembic
if "+asyncpg" in database_url:
    database_url = database_url.replace("+asyncpg", "")

config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the provided connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    Uses asyncpg for async PostgreSQL connectivity.
    """
    # Get the async database URL
    async_url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)

    # Ensure we use asyncpg driver
    if "+asyncpg" not in async_url:
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://")

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = async_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
