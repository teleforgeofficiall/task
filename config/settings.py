"""
TASKHUB — Centralized Configuration
All settings are loaded from environment variables.
Never hardcode secrets — use .env file or Render environment panel.
"""
from __future__ import annotations

import sys
from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ─── Bot ────────────────────────────────────────────────────────────────
    BOT_TOKEN: str = Field(..., description="Telegram Bot Token from @BotFather")
    BOT_NAME: str = Field(default="TASKHUB", description="Display name shown in messages")
    BOT_USERNAME: str = Field(default="", description="Bot username without @")
    WEBHOOK_URL: str = Field(default="", description="Webhook URL (leave empty for long-polling)")
    WEBHOOK_SECRET: str = Field(default="", description="Webhook secret token")
    PORT: int = Field(default=8000, description="FastAPI/Uvicorn listen port")
    ENVIRONMENT: str = Field(default="production", description="development | production")

    # ─── Admins ─────────────────────────────────────────────────────────────
    ADMIN_IDS: str = Field(
        default="",
        description="Comma-separated admin Telegram user IDs (e.g. 123456,789012)",
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def coerce_admin_ids(cls, v: object) -> str:
        return str(v) if v else ""

    @property
    def admin_id_list(self) -> List[int]:
        return [
            int(x.strip())
            for x in self.ADMIN_IDS.split(",")
            if x.strip().isdigit()
        ]

    # ─── Database (MySQL) ───────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="",
        description="MySQL connection string (e.g. mysql+aiomysql://user:pass@localhost:3306/db)",
    )
    DB_HOST: str = Field(default="localhost", description="MySQL host")
    DB_PORT: int = Field(default=3306, description="MySQL port")
    DB_USER: str = Field(default="taskhub_user", description="MySQL user")
    DB_PASSWORD: str = Field(default="", description="MySQL password")
    DB_NAME: str = Field(default="taskhub_db", description="MySQL database name")

    # Legacy MongoDB settings (kept for backward compatibility during migration)
    MONGO_URL: str = Field(default="", description="MongoDB Atlas connection string (legacy)")
    MONGO_MOCK: bool = Field(default=False, description="Use MongoDB mock (legacy)")

    # ─── Runtime flags ───────────────────────────────────────────────────────
    DISABLE_TELEGRAM_NETWORK: bool = Field(
        default=False,
        description="If true, skip webhook/polling network calls (dev/local verification only).",
    )

    # ─── Redis (optional caching) ────────────────────────────────────────────
    REDIS_URL: str = Field(default="", description="Redis URL (optional)")

    # ─── Finance ────────────────────────────────────────────────────────────
    MIN_WITHDRAW: float = Field(default=10.0, description="Minimum withdrawal amount (₹)")
    MAX_WITHDRAW: float = Field(default=10000.0, description="Maximum withdrawal amount (₹)")

    # ─── Rate Limiting ──────────────────────────────────────────────────────
    RATE_LIMIT_MESSAGES: int = Field(default=3, description="Max messages per window")
    RATE_LIMIT_WINDOW: int = Field(default=3, description="Rate limit window in seconds")
    FLOOD_MUTE_SECONDS: int = Field(default=30, description="Auto-mute duration on flood")

    # ─── Referral System ────────────────────────────────────────────────────
    DEFAULT_REFERRAL_MODE: str = Field(
        default="random",
        description="fixed | random | smart",
    )
    DEFAULT_FIXED_REWARD: float = Field(default=0.5, description="Fixed referral reward (₹)")
    DEFAULT_RANDOM_MIN: float = Field(default=0.5, description="Random reward minimum (₹)")
    DEFAULT_RANDOM_MAX: float = Field(default=5.0, description="Random reward maximum (₹)")

    # ─── Game ────────────────────────────────────────────────────────────────
    SNAP_CLOSE_HOUR: int = Field(default=9, description="IST hour to close Snap Pick betting")
    SNAP_CLOSE_MIN: int = Field(default=45, description="IST minute to close betting")
    SNAP_RESULT_HOUR: int = Field(default=10, description="IST hour to declare result")
    SNAP_RESULT_MIN: int = Field(default=0, description="IST minute to declare result")
    SNAP_OPEN_HOUR: int = Field(default=10, description="IST hour to re-open betting")
    SNAP_OPEN_MIN: int = Field(default=30, description="IST minute to re-open betting")

    # ─── Security ───────────────────────────────────────────────────────────
    FRAUD_SCORE_THRESHOLD: int = Field(
        default=50,
        description="Fraud score above this blocks referral rewards",
    )
    FRAUD_AUTO_BAN_THRESHOLD: int = Field(
        default=100,
        description="Fraud score above this triggers auto-ban alert",
    )

    # ─── Backup ──────────────────────────────────────────────────────────────
    BACKUP_DIR: str = Field(default="/app/backups", description="Directory to store DB backups")
    BACKUP_RETENTION_DAYS: int = Field(
        default=30, description="Number of days to keep old backups",
    )

    # ─── GitHub Backup ────────────────────────────────────────────────────────
    GIT_BACKUP_REPO: str = Field(default="", description="GitHub repo for backups (owner/repo)")
    GIT_BACKUP_TOKEN: str = Field(default="", description="GitHub PAT with contents:write")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_webhook_mode(self) -> bool:
        return bool(self.WEBHOOK_URL)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:
        print(f"[TASKHUB] ❌ Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


# Module-level singleton — import this everywhere
settings = get_settings()
