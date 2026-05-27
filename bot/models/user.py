"""
UserModel — Pydantic v2 model representing a TASKHUB user.
All optional fields have safe defaults so legacy DB documents load without error.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _epoch_str() -> str:
    return "1970-01-01T00:00:00+00:00"


class UserModel(BaseModel):
    # ─── Identity ────────────────────────────────────────────────────────────
    user_id: int
    username: Optional[str] = None
    first_name: str
    phone_number: Optional[str] = None

    # ─── Financials ──────────────────────────────────────────────────────────
    balance: float = 0.0
    lifetime_earnings: float = 0.0
    referral_earnings: float = 0.0
    withdrawal_count: int = 0

    # ─── Referrals ───────────────────────────────────────────────────────────
    referrer: Optional[int] = None
    referrals: List[int] = Field(default_factory=list)
    unclaimed_referrals: List[int] = Field(default_factory=list)
    rewarded_referrals: List[int] = Field(default_factory=list)
    ref_tier1_count: int = 0
    ref_tier2_count: int = 0
    ref_tier3_count: int = 0

    # ─── Tasks ───────────────────────────────────────────────────────────────
    completed_tasks: List[int] = Field(default_factory=list)
    last_task_completion_time: str = Field(default_factory=_epoch_str)

    # ─── Daily Bonus ─────────────────────────────────────────────────────────
    last_bonus_date: Optional[str] = None
    last_daily_bonus: Optional[str] = None

    # ─── Activity ────────────────────────────────────────────────────────────
    joined_at: str = Field(default_factory=_now_ist)
    last_active_date: str = Field(default_factory=_now_ist)

    # ─── Status ──────────────────────────────────────────────────────────────
    banned: bool = False
    ban_reason: Optional[str] = None
    warnings: int = 0
    withdraw_locked: bool = False
    active_penalties: List[str] = Field(default_factory=list)

    # ─── Notifications ────────────────────────────────────────────────────────
    notifications: List[str] = Field(default_factory=list)

    # ─── Referral Claim Tracking ──────────────────────────────────────────────
    referral_reward_claimed: bool = False

    # ─── Casino Profiling ────────────────────────────────────────────────────
    user_meta: Optional[dict] = None
    current_session_start: Optional[str] = None
    session_total_bets: int = 0
    session_total_wins: int = 0
    session_total_losses: int = 0
    session_net: float = 0.0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    longest_win_streak: int = 0
    longest_loss_streak: int = 0
    last_game_played: Optional[str] = None
    total_deposits: float = 0.0
    total_withdrawals: float = 0.0
    net_profit: float = 0.0
    total_bets_count: int = 0
    total_wins_count: int = 0
    avg_bet_size: float = 0.0
    rage_bet_count: int = 0
    last_bet_time: Optional[str] = None

    # ─── Device / Security ───────────────────────────────────────────────────
    device_verified: bool = False
    fraud_score: int = 0
    is_flagged: bool = False
    flag_reason: Optional[str] = None

    class Config:
        # Allows creating from MongoDB dicts without strict validation
        populate_by_name = True

    @field_validator("lifetime_earnings", mode="before")
    @classmethod
    def default_lifetime(cls, v: object, info: object) -> float:
        # If lifetime_earnings is None or 0 fall back to balance
        if v is None:
            return 0.0
        return float(v)

    def to_dict(self) -> dict:
        """Return a plain dict suitable for MongoDB insertion/update."""
        return self.model_dump()

    @classmethod
    def from_mongo(cls, data: dict) -> "UserModel":
        """Create model from a raw MongoDB document (removes _id)."""
        data = dict(data)
        data.pop("_id", None)
        return cls(**data)

    def touch(self) -> None:
        """Update last_active_date to now (IST)."""
        self.last_active_date = _now_ist()
