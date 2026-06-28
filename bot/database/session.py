"""
session.py — SQLAlchemy async engine & session factory for MySQL.

Usage:
    from bot.database.session import get_session, init_db, close_db

    async with get_session() as session:
        result = await session.execute(select(UserTable))
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, AsyncIterator, Optional

from sqlalchemy import text
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
        if url.startswith("mysql://"):
            url = url.replace("mysql://", "mysql+aiomysql://", 1)
        elif url.startswith("mysql+aiomysql://"):
            pass
        elif url.startswith("postgresql"):
            url = url.replace("postgresql+asyncpg://", "mysql+aiomysql://", 1)
            url = url.replace("postgresql+psycopg://", "mysql+aiomysql://", 1)
            url = url.replace("postgresql://", "mysql+aiomysql://", 1)
            url = url.replace("postgres://", "mysql+aiomysql://", 1)
            url = url.split("?")[0]
        return url
    # Fallback to SQLite for local development
    if not settings.is_production:
        return "sqlite+aiosqlite:///./taskhub.db"
    # Production: build from components
    url = f"mysql+aiomysql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    return url


async def ensure_database_exists() -> None:
    """Auto-create database, user, and grant privileges using MySQL root."""
    root_pass = settings.MYSQL_ROOT_PASSWORD
    if not root_pass:
        logger.info("MYSQL_ROOT_PASSWORD not set — skipping auto DB creation")
        return

    # Parse actual credentials from DATABASE_URL
    db_name = settings.DB_NAME
    db_user = settings.DB_USER
    db_pass = settings.DB_PASSWORD
    host = settings.DB_HOST

    url = settings.DATABASE_URL
    if url and "mysql" in url:
        clean = url.replace("mysql+aiomysql://", "").replace("mysql://", "")
        if "@" in clean:
            user_pass, rest = clean.split("@", 1)
            if ":" in user_pass:
                db_user = user_pass.split(":")[0]
                db_pass = ":".join(user_pass.split(":")[1:])
            host_part = rest.split("/")[0]
            if ":" in host_part:
                host = host_part.split(":")[0]
            else:
                host = host_part
            name_part = rest.split("/")[1] if "/" in rest else db_name
            if name_part:
                db_name = name_part.split("?")[0]

    root_url = f"mysql+aiomysql://root:{root_pass}@{host}:{settings.DB_PORT}"
    engine = create_async_engine(root_url, echo=False, pool_pre_ping=False)

    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
            await conn.execute(text(
                f"CREATE USER IF NOT EXISTS '{db_user}'@'{host}' "
                f"IDENTIFIED BY '{db_pass}'"
            ))
            await conn.execute(text(
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'{host}'"
            ))
            await conn.execute(text("FLUSH PRIVILEGES"))
        logger.info("Ensured database '%s' and user '%s' exist", db_name, db_user)
    except Exception as exc:
        logger.warning("Could not auto-create database/user (may already exist): %s", exc)
    finally:
        await engine.dispose()


async def init_db() -> None:
    """Initialize the engine and session factory. Creates tables if they don't exist."""
    global _engine, _session_factory

    if _engine is not None:
        return

    async with _init_lock:
        if _engine is not None:
            return

        database_url = get_database_url()
        is_mysql = "mysql" in database_url
        logger.info("Initializing database connection: %s", database_url)

        if is_mysql:
            _engine = create_async_engine(
                database_url,
                pool_size=25,
                max_overflow=10,
                pool_recycle=3600,
                echo=False,
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
        if is_mysql:
            await _migrate_mysql_schema(_engine)
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

        # ── Tasks table: add missing columns ──
        task_columns_sqlite: dict[str, str] = {
            "completion_count": "INTEGER DEFAULT 0",
            "video_url": "TEXT DEFAULT ''",
            "steps": "TEXT DEFAULT NULL",
            "color": "VARCHAR(20) DEFAULT '#7b5ef8'",
            "color2": "VARCHAR(20) DEFAULT '#5a3fd6'",
            "duration_text": "VARCHAR(50) DEFAULT '15 min'",
            "is_multi_reward": "INTEGER DEFAULT 0",
            "offer_url": "TEXT DEFAULT ''",
            "referrer_reward": "FLOAT DEFAULT 0.0",
            "completer_reward": "FLOAT DEFAULT 0.0",
            "max_completers": "INTEGER DEFAULT 0",
            "current_completers": "INTEGER DEFAULT 0",
            "expires_at": "VARCHAR(50) DEFAULT NULL",
        }
        def _get_task_cols_sqlite(sync_conn):
            return {c["name"] for c in inspect(sync_conn).get_columns("tasks")}
        task_existing = await conn.run_sync(_get_task_cols_sqlite)
        for col_name, col_type in task_columns_sqlite.items():
            if col_name not in task_existing:
                try:
                    await conn.execute(sa_text(
                        f'ALTER TABLE tasks ADD COLUMN {col_name} {col_type}'
                    ))
                    logger.info("Added column tasks.%s", col_name)
                except Exception as exc:
                    logger.warning("Could not add column tasks.%s: %s", col_name, exc)


async def _migrate_mysql_schema(engine) -> None:
    """Add missing columns to existing MySQL tables."""
    import sqlalchemy as sa
    from sqlalchemy import inspect, text as sa_text

    # ── Users table: new casino profiling columns ──
    user_columns: dict[str, str] = {
        "user_meta": "JSON DEFAULT (JSON_OBJECT())",
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
                        f'ALTER TABLE users ADD COLUMN `{col_name}` {col_type}'
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
                        f'ALTER TABLE withdrawals ADD COLUMN `{col_name}` {col_type}'
                    ))
                    logger.info("Added column withdrawals.%s", col_name)
                except Exception as exc:
                    logger.warning("Could not add column withdrawals.%s: %s", col_name, exc)

        # ── Tasks table: add missing columns ──
        task_columns: dict[str, str] = {
            "completion_count": "INTEGER DEFAULT 0",
            "video_url": "TEXT DEFAULT ''",
            "steps": "JSON DEFAULT NULL",
            "color": "VARCHAR(20) DEFAULT '#7b5ef8'",
            "color2": "VARCHAR(20) DEFAULT '#5a3fd6'",
            "duration_text": "VARCHAR(50) DEFAULT '15 min'",
            "is_multi_reward": "BOOLEAN DEFAULT FALSE",
            "offer_url": "TEXT DEFAULT ''",
            "referrer_reward": "FLOAT DEFAULT 0.0",
            "completer_reward": "FLOAT DEFAULT 0.0",
            "max_completers": "INTEGER DEFAULT 0",
            "current_completers": "INTEGER DEFAULT 0",
            "expires_at": "VARCHAR(50) DEFAULT NULL",
        }
        def _get_task_cols(sync_conn):
            return {c["name"] for c in inspect(sync_conn).get_columns("tasks")}
        task_existing = await conn.run_sync(_get_task_cols)
        for col_name, col_type in task_columns.items():
            if col_name not in task_existing:
                try:
                    await conn.execute(sa_text(
                        f'ALTER TABLE tasks ADD COLUMN `{col_name}` {col_type}'
                    ))
                    logger.info("Added column tasks.%s", col_name)
                except Exception as exc:
                    logger.warning("Could not add column tasks.%s: %s", col_name, exc)

        # ── Proofs table: change proof_file_id from TEXT to LONGTEXT ──
        try:
            def _get_proof_cols(sync_conn):
                return {c["name"] for c in inspect(sync_conn).get_columns("proofs")}
            proof_existing = await conn.run_sync(_get_proof_cols)
            if "proof_file_id" in proof_existing:
                col_type = proof_existing["proof_file_id"].type
                if hasattr(col_type, 'length') and col_type.length and col_type.length < 100000:
                    await conn.execute(sa_text(
                        'ALTER TABLE proofs MODIFY COLUMN `proof_file_id` LONGTEXT NOT NULL'
                    ))
                    logger.info("Altered proofs.proof_file_id to LONGTEXT")
        except Exception as exc:
            logger.warning("Could not alter proofs.proof_file_id: %s", exc)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
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
        logger.info("MySQL connection closed.")


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



