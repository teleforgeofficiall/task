"""
data_exporter.py — SQLAlchemy-based table export/import.
Works through any MySQL connection.
Uses ORM for import so JSON columns are handled automatically.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from bot.database.models_sql import Base
from bot.database.repository import Repository

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))

TABLE_NAMES = [
    "settings", "game_state", "users", "tasks", "proofs",
    "withdrawals", "redeem_codes", "transactions", "admin_logs",
    "game_rounds", "backup_records", "game_sessions",
    "device_fingerprints", "jackpot_events", "retention_events",
]


def _all_subclasses(cls):
    """Get all recursive subclasses of a class."""
    for sub in cls.__subclasses__():
        yield sub
        yield from _all_subclasses(sub)


async def export_images_settings(session: AsyncSession) -> Dict[str, str]:
    """Export all img_* settings as a plain dict."""
    repo = Repository(session)
    all_settings = await repo.get_all_settings()
    return {k: v for k, v in all_settings.items() if k.startswith("img_")}


async def import_images_settings(session: AsyncSession, images: Dict[str, str]) -> None:
    """Restore img_* settings into the settings table."""
    repo = Repository(session)
    for key, value in images.items():
        await repo.update_setting(key, value)


async def export_all_tables(session: AsyncSession) -> Dict[str, List[Dict[str, Any]]]:
    """Export all data tables as JSON-serializable dicts."""
    result: Dict[str, List[Dict[str, Any]]] = {}
    for table_name in TABLE_NAMES:
        table = Base.metadata.tables.get(table_name)
        order_col = "id"
        if table is not None:
            pk = next(iter(table.primary_key), None)
            if pk is not None:
                order_col = pk.name
        rows = await session.execute(text(f"SELECT * FROM {table_name} ORDER BY {order_col}"))
        columns = list(rows.keys())
        table_data = []
        for row in rows.fetchall():
            row_dict = dict(zip(columns, row))
            _serialize_row(row_dict)
            table_data.append(row_dict)
        result[table_name] = table_data
        logger.info("Exported %d rows from %s", len(table_data), table_name)
    return result


async def import_all_tables(session: AsyncSession, data: Dict[str, List[Dict[str, Any]]]) -> None:
    """Clear all tables via DELETE and insert exported data back via ORM."""
    for table_name in TABLE_NAMES:
        rows = data.get(table_name, [])
        if rows:
            _prepare_rows(table_name, rows)

    model_map = {}
    for sub in _all_subclasses(Base):
        if hasattr(sub, "__tablename__") and sub.__tablename__ in TABLE_NAMES:
            model_map[sub.__tablename__] = sub

    seq_tables = [
        "users", "tasks", "proofs", "withdrawals", "redeem_codes",
        "transactions", "admin_logs", "game_rounds", "backup_records",
        "game_sessions", "device_fingerprints", "jackpot_events", "retention_events",
    ]

    async with session.begin():
        for table_name in TABLE_NAMES:
            await session.execute(text(f"DELETE FROM {table_name}"))
        for table_name in seq_tables:
            try:
                await session.execute(text(f"ALTER TABLE {table_name} AUTO_INCREMENT = 1"))
            except Exception:
                pass

    async with session.begin():
        for table_name in TABLE_NAMES:
            rows = data.get(table_name, [])
            if not rows:
                continue
            model_class = model_map.get(table_name)
            if model_class is None:
                logger.warning("No model class found for %s, skipping", table_name)
                continue
            for row_data in rows:
                instance = model_class(**row_data)
                session.add(instance)
            await session.flush()
            logger.info("Imported %d rows into %s", len(rows), table_name)
    logger.info("Database restore complete")


def _serialize_row(row: Dict[str, Any]) -> None:
    """Convert non-serializable types to JSON-compatible in-place."""
    for key, value in list(row.items()):
        if isinstance(value, datetime):
            row[key] = value.isoformat()
        elif isinstance(value, (list, dict)):
            row[key] = json.dumps(value, default=str)
        elif value is None:
            pass
        elif not isinstance(value, (str, int, float, bool)):
            row[key] = str(value)


def _prepare_rows(table_name: str, rows: List[Dict[str, Any]]) -> None:
    """Convert JSON strings back to Python objects in-place.

    Skips settings table entirely — its value column is VARCHAR,
    so dicts/lists must remain as JSON strings.
    """
    if table_name == "settings":
        return
    for row in rows:
        for key, value in list(row.items()):
            if isinstance(value, str) and len(value) > 1:
                if (value[0] == "[" and value[-1] == "]") or (value[0] == "{" and value[-1] == "}"):
                    try:
                        row[key] = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        pass
