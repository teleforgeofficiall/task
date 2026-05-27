"""
models_sql.py — SQLAlchemy 2.0 ORM models for PostgreSQL.

Mirrors the MongoDB schema exactly. Each table corresponds to a previous MongoDB collection.
Settings and GameState use a key-value JSON pattern for flexibility.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, BigInteger, Float, String, Boolean, DateTime,
    Text, JSON, ForeignKey, UniqueConstraint, Index, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(IST)


class Base(DeclarativeBase):
    pass


# ─── Users ────────────────────────────────────────────────────────────────────

class UserTable(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Financials
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_earnings: Mapped[float] = mapped_column(Float, default=0.0)
    referral_earnings: Mapped[float] = mapped_column(Float, default=0.0)
    withdrawal_count: Mapped[int] = mapped_column(Integer, default=0)

    # Referrals
    referrer: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    referrals: Mapped[List[int]] = mapped_column(JSON, default=list)
    unclaimed_referrals: Mapped[List[int]] = mapped_column(JSON, default=list)
    rewarded_referrals: Mapped[List[int]] = mapped_column(JSON, default=list)
    ref_tier1_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_tier2_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_tier3_count: Mapped[int] = mapped_column(Integer, default=0)

    # Tasks
    completed_tasks: Mapped[List[int]] = mapped_column(JSON, default=list)
    last_task_completion_time: Mapped[str] = mapped_column(String(50), default="1970-01-01T00:00:00+00:00")

    # Daily Bonus
    last_bonus_date: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_daily_bonus: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Activity
    joined_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())
    last_active_date: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())

    # Status
    banned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings: Mapped[int] = mapped_column(Integer, default=0)
    withdraw_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    active_penalties: Mapped[List[str]] = mapped_column(JSON, default=list)

    # Notifications
    notifications: Mapped[List[str]] = mapped_column(JSON, default=list)

    # Device / Security
    device_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Referral claim tracking
    referral_reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_users_lifetime_earnings", "lifetime_earnings"),
        Index("ix_users_joined_at", "joined_at"),
        Index("ix_users_last_active_date", "last_active_date"),
    )


# ─── Tasks ────────────────────────────────────────────────────────────────────

class TaskTable(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(20), default="manual", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    guide: Mapped[str] = mapped_column(Text, default="")
    reward: Mapped[float] = mapped_column(Float, nullable=False)
    image: Mapped[str] = mapped_column(Text, default="")
    media_type: Mapped[str] = mapped_column(String(10), default="photo")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())

    # Channel task specific
    channel_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    channel_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    channel_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    channel_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


# ─── Proofs (Task Submissions) ─────────────────────────────────────────────────

class ProofTable(Base):
    __tablename__ = "proofs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(Integer, nullable=False)
    proof_file_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), default="photo")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())
    reviewed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_proofs_user_task", "user_id", "task_id"),
        Index("ix_proofs_status_date", "status", "date"),
    )


# ─── Withdrawals ──────────────────────────────────────────────────────────────

class WithdrawalTable(Base):
    __tablename__ = "withdrawals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="upi", index=True)
    upi_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    redeem_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())
    approved_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("ix_withdrawals_user_date", "user_id", "date"),
        Index("ix_withdrawals_method_status", "method", "status"),
    )


# ─── Transactions ─────────────────────────────────────────────────────────────

class TransactionTable(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat(), index=True)
    ref_id: Mapped[str] = mapped_column(String(100), default="")

    __table_args__ = (
        Index("ix_transactions_user_time", "user_id", "timestamp"),
        Index("ix_transactions_type_time", "type", "timestamp"),
    )


# ─── Admin Logs ───────────────────────────────────────────────────────────────

class AdminLogTable(Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())

    __table_args__ = (
        Index("ix_admin_logs_admin_time", "admin_id", "timestamp"),
    )


# ─── Settings (key-value store for flexibility) ───────────────────────────────

class SettingTable(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ─── Game State (single-row JSON blob) ────────────────────────────────────────

class GameStateTable(Base):
    __tablename__ = "game_state"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, default="state")
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


# ─── Game Rounds (Analytics Log) ────────────────────────────────────────────

class GameRoundTable(Base):
    __tablename__ = "game_rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    game: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    bet: Mapped[float] = mapped_column(Float, nullable=False)
    payout: Mapped[float] = mapped_column(Float, nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=0.0)
    won: Mapped[bool] = mapped_column(Boolean, default=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat(), index=True)

    __table_args__ = (
        Index("ix_game_rounds_user_time", "user_id", "timestamp"),
        Index("ix_game_rounds_game_time", "game", "timestamp"),
    )


# ─── Backup Records ───────────────────────────────────────────────────────────

class BackupRecordTable(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.now(IST).isoformat())
