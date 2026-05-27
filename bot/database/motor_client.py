"""
Motor (async MongoDB) client singleton.
Call get_db() anywhere to obtain the database handle.
Indexes are created on first connect via ensure_indexes().
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from config.settings import settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None
_connect_lock = asyncio.Lock()


async def connect() -> None:
    """Open Motor connection and create all indexes."""
    global _client, _database

    if _database is not None and _client is not None:
        return

    if settings.MONGO_MOCK:
        # Local/dev verification mode: in-memory async mock (no external Mongo service required).
        try:
            from mongomock_motor import AsyncMongoMockClient  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "MONGO_MOCK is enabled but mongomock-motor is not installed. "
                "Install it or disable MONGO_MOCK."
            ) from exc

        _client = AsyncMongoMockClient()  # type: ignore[assignment]
        _database = _client[settings.DB_NAME]
        logger.info("✅ MongoDB mock enabled — DB: %s", settings.DB_NAME)
        await _ensure_indexes(_database)
        return

    logger.info("Connecting to MongoDB…")
    _client = AsyncIOMotorClient(
        settings.MONGO_URL,
        serverSelectionTimeoutMS=10_000,
        maxPoolSize=50,
        minPoolSize=5,
    )
    _database = _client[settings.DB_NAME]

    # Verify connection
    await _client.admin.command("ping")
    logger.info("✅ MongoDB connected — DB: %s", settings.DB_NAME)

    await _ensure_indexes(_database)


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create all performance and uniqueness indexes."""
    try:
        # users
        await db.users.create_index("user_id", unique=True, background=True)
        await db.users.create_index("username", background=True)
        await db.users.create_index([("joined_at", DESCENDING)], background=True)
        await db.users.create_index([("last_active_date", DESCENDING)], background=True)
        await db.users.create_index([("lifetime_earnings", DESCENDING)], background=True)
        await db.users.create_index("fraud_score", background=True)
        await db.users.create_index("banned", background=True)

        # tasks
        await db.tasks.create_index("id", unique=True, background=True)
        await db.tasks.create_index("is_active", background=True)
        await db.tasks.create_index("task_type", background=True)

        # proofs
        await db.proofs.create_index("id", unique=True, background=True)
        await db.proofs.create_index([("status", ASCENDING), ("date", DESCENDING)], background=True)
        await db.proofs.create_index([("user_id", ASCENDING), ("task_id", ASCENDING)], background=True)

        # withdrawals
        await db.withdrawals.create_index("id", unique=True, background=True)
        await db.withdrawals.create_index([("user_id", ASCENDING), ("date", DESCENDING)], background=True)
        await db.withdrawals.create_index([("status", ASCENDING)], background=True)

        # transactions
        await db.transactions.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)], background=True)
        await db.transactions.create_index([("type", ASCENDING), ("timestamp", DESCENDING)], background=True)

        # admin_logs
        await db.admin_logs.create_index([("admin_id", ASCENDING), ("timestamp", DESCENDING)], background=True)
        await db.admin_logs.create_index([("action", ASCENDING)], background=True)

        logger.info("✅ MongoDB indexes verified")
    except Exception as exc:
        logger.warning("Index creation warning (may already exist): %s", exc)


async def close_db() -> None:
    """Close Motor connection gracefully."""
    global _client, _database
    if _client:
        # Mock client does not always implement close()
        close = getattr(_client, "close", None)
        if callable(close):
            close()
        _client = None
        _database = None
        logger.info("MongoDB connection closed")


async def get_db() -> AsyncIOMotorDatabase:
    """
    Return the active database handle.

    Compatibility note:
    The existing codebase uses `await get_db()` across handlers/services; therefore get_db is async.
    If the database is not connected yet, this will connect lazily (exactly once) and ensure indexes.
    """
    if _database is not None:
        return _database

    async with _connect_lock:
        # Double-check after acquiring the lock.
        if _database is None:
            await connect()

    if _database is None:
        raise RuntimeError("Database initialisation failed")
    return _database
