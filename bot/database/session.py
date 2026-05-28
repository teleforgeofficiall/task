"""
session.py — SQLAlchemy async engine & session factory for PostgreSQL.

Usage:
    from bot.database.session import get_session, init_db, close_db

    async with get_session() as session:
        result = await session.execute(select(UserTable))
"""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import settings

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
_init_lock = asyncio.Lock()


def get_database_url() -> str:
    """Return the async database connection string."""
    url = settings.DATABASE_URL
    if url:
        if not url.startswith("postgresql+asyncpg://") and "postgres" in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url
    # Fallback to SQLite for local development
    if not settings.is_production:
        return "sqlite+aiosqlite:///./taskhub.db"
    # Production: build from components
    return f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"


async def init_db() -> None:
    """Initialize the engine and session factory. Creates tables if they don't exist."""
    global _engine, _session_factory

    if _engine is not None:
        return

    async with _init_lock:
        if _engine is not None:
            return

        database_url = get_database_url()
        is_postgres = "postgres" in database_url
        logger.info("Initializing database connection: %s", database_url)

        if is_postgres:
            _engine = create_async_engine(
                database_url,
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
                connect_args={
                    "command_timeout": 30,
                    "ssl": "require" if settings.is_production else "prefer",
                },
            )
        else:
            _engine = create_async_engine(
                database_url,
                echo=False,
                connect_args={"check_same_thread": False},
            )

        _session_factory = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Create all tables
        from bot.database.models_sql import Base
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Run schema migrations for existing tables
        if is_postgres:
            await _migrate_postgres_schema(_engine)
        else:
            await _migrate_sqlite_schema(_engine)

        logger.info("Database tables created and verified.")


async def _migrate_sqlite_schema(engine) -> None:
    """Add missing columns to existing SQLite tables."""
    import sqlalchemy as sa
    from sqlalchemy import inspect, text as sa_text

    # ── Withdrawals table: add stars & channel_link columns ──
    wd_columns_sqlite: dict[str, str] = {
        "stars": "INTEGER DEFAULT 0",
        "channel_link": "VARCHAR(500) DEFAULT ''",
    }

    async with engine.begin() as conn:
        def _get_wd_cols_sqlite(sync_conn):
            return {c["name"] for c in inspect(sync_conn).get_columns("withdrawals")}
        existing = await conn.run_sync(_get_wd_cols_sqlite)

        for col_name, col_type in wd_columns_sqlite.items():
            if col_name not in existing:
                try:
                    await conn.execute(sa_text(
                        f'ALTER TABLE withdrawals ADD COLUMN {col_name} {col_type}'
                    ))
                    logger.info("Added column withdrawals.%s", col_name)
                except Exception as exc:
                    logger.warning("Could not add column withdrawals.%s: %s", col_name, exc)


async def _migrate_postgres_schema(engine) -> None:
    """Add missing columns to existing PostgreSQL tables."""
    import sqlalchemy as sa
    from sqlalchemy import inspect, text as sa_text

    # ── Users table: new casino profiling columns ──
    user_columns: dict[str, str] = {
        "user_meta": "JSONB DEFAULT '{}'::jsonb",
        "current_session_start": "VARCHAR(50)",
        "session_total_bets": "INTEGER DEFAULT 0",
        "session_total_wins": "INTEGER DEFAULT 0",
        "session_total_losses": "INTEGER DEFAULT 0",
        "session_net": "FLOAT DEFAULT 0.0",
        "consecutive_losses": "INTEGER DEFAULT 0",
        "consecutive_wins": "INTEGER DEFAULT 0",
        "longest_win_streak": "INTEGER DEFAULT 0",
        "longest_loss_streak": "INTEGER DEFAULT 0",
        "last_game_played": "VARCHAR(20)",
        "total_deposits": "FLOAT DEFAULT 0.0",
        "total_withdrawals": "FLOAT DEFAULT 0.0",
        "net_profit": "FLOAT DEFAULT 0.0",
        "total_bets_count": "INTEGER DEFAULT 0",
        "total_wins_count": "INTEGER DEFAULT 0",
        "avg_bet_size": "FLOAT DEFAULT 0.0",
        "rage_bet_count": "INTEGER DEFAULT 0",
        "last_bet_time": "VARCHAR(50)",
    }

    async with engine.begin() as conn:
        # Get existing columns
        def _get_cols(sync_conn):
            return {c["name"] for c in inspect(sync_conn).get_columns("users")}
        existing = await conn.run_sync(_get_cols)

        for col_name, col_type in user_columns.items():
            if col_name not in existing:
                try:
                    await conn.execute(sa_text(
                        f'ALTER TABLE users ADD COLUMN "{col_name}" {col_type}'
                    ))
                    logger.info("Added column users.%s", col_name)
                except Exception as exc:
                    logger.warning("Could not add column users.%s: %s", col_name, exc)

        # ── Withdrawals table: add stars & channel_link columns ──
        wd_columns: dict[str, str] = {
            "stars": "INTEGER DEFAULT 0",
            "channel_link": "VARCHAR(500) DEFAULT ''",
        }

        def _get_wd_cols(sync_conn):
            return {c["name"] for c in inspect(sync_conn).get_columns("withdrawals")}
        wd_existing = await conn.run_sync(_get_wd_cols)

        for col_name, col_type in wd_columns.items():
            if col_name not in wd_existing:
                try:
                    await conn.execute(sa_text(
                        f'ALTER TABLE withdrawals ADD COLUMN "{col_name}" {col_type}'
                    ))
                    logger.info("Added column withdrawals.%s", col_name)
                except Exception as exc:
                    logger.warning("Could not add column withdrawals.%s: %s", col_name, exc)

        # ── New tables that might not have been created ──
        # (GameSessionTable, JackpotEventTable, RetentionEventTable are handled by create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async session. Initializes DB on first call."""
    if _session_factory is None:
        await init_db()

    async with _session_factory() as session:  # type: ignore[union-attr]
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncSession:
    """Return a standalone session (for backward compatibility with get_db() calls)."""
    if _session_factory is None:
        await init_db()
    return _session_factory()  # type: ignore[union-attr]


async def close_db() -> None:
    """Dispose the engine gracefully."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("PostgreSQL connection closed.")


async def check_db_health() -> bool:
    """Health check — run a simple query to verify DB connectivity."""
    try:
        async with get_session() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return False


async def reset_all_data() -> None:
    """Drop all tables and recreate them with default seed data."""
    global _engine, _session_factory
    from bot.database.models_sql import Base

    if _engine is None:
        await init_db()

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("All tables dropped.")

    # Recreate and seed
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed defaults
    from bot.database.repository import Repository
    db = await get_db()
    repo = Repository(db)
    await repo.ensure_defaults()

    logger.info("Database reset complete — all tables recreated and seeded.")
