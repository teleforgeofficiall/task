"""
alembic/env.py — Alembic migration environment configuration.

Auto-discovers SQLAlchemy models from bot.database.models_sql
and generates migrations for PostgreSQL schema changes.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Alembic Config object
config = context.config

# Set up logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect them
from bot.database.models_sql import Base  # noqa: E402

target_metadata = Base.metadata


def get_url() -> str:
    """Get database URL from config or environment."""
    url = config.get_main_option("sqlalchemy.url")
    # Allow override via environment variable
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with a connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' async mode."""
    url = get_url()
    if url:
        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+aiomysql://", 1)
        elif not url.startswith("mysql+aiomysql://"):
            url = url.replace("postgresql+asyncpg://", "mysql+aiomysql://", 1)
            url = url.replace("postgresql+psycopg://", "mysql+aiomysql://", 1)
            url = url.replace("postgresql://", "mysql+aiomysql://", 1)
            url = url.replace("postgres://", "mysql+aiomysql://", 1)

    connectable = create_async_engine(url, poolclass=pool.NullPool)

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
