"""
reset_database.py — Standalone script to reset all database tables and seed defaults.

Run from terminal (NOT from bot admin panel / Telegram):
    cd /opt/taskhub && venv/bin/python scripts/reset_database.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from bot.database.models_sql import Base

logger = logging.getLogger("reset")


def _get_sync_url() -> str:
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        for old, new in [
            ("postgresql+asyncpg://", "postgresql://"),
            ("sqlite+aiosqlite://", "sqlite://"),
        ]:
            if db_url.startswith(old):
                return db_url.replace(old, new, 1)
        return db_url
    user = os.getenv("DB_USER", "taskhub_user")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db = os.getenv("DB_NAME", "taskhub_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _drop_and_create(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS {} CASCADE".format(",".join(Base.metadata.tables))))
        Base.metadata.create_all(conn)


async def _seed_defaults():
    from bot.database.session import init_db, get_db, close_db
    from bot.database.repository import Repository
    from bot.admin.panel import refresh_admin_ids

    await init_db()
    db = await get_db()
    repo = Repository(db)
    await repo.ensure_defaults()
    try:
        await refresh_admin_ids()
    except Exception:
        pass
    await close_db()


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sync_url = _get_sync_url()
    host_part = sync_url.split("@")[-1] if "@" in sync_url else sync_url
    is_sqlite = "sqlite" in sync_url

    if not is_sqlite:
        try:
            import psycopg2  # noqa: F401
        except ImportError:
            print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
            sys.exit(1)

    confirm = input("WARNING: This will DELETE ALL DATA. Type 'reset' to confirm: ")
    if confirm != "reset":
        print("Cancelled.")
        return

    print(f"Connecting to {host_part} ...")
    engine = create_engine(sync_url, pool_pre_ping=False)
    try:
        _drop_and_create(engine)
        print("All tables dropped and recreated.")
    except Exception as exc:
        print(f"DDL failed: {exc}")
        sys.exit(1)
    finally:
        engine.dispose()

    asyncio.run(_seed_defaults())
    print("Default settings seeded.")
    print("Database reset complete!")


if __name__ == "__main__":
    main()
