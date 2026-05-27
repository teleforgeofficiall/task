"""TransactionModel — Immutable ledger entry for every balance change."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

IST = timezone(timedelta(hours=5, minutes=30))

# Transaction type constants
TX_TASK_REWARD = "task_reward"
TX_REFERRAL_REWARD = "referral_reward"
TX_AD_REWARD = "ad_reward"
TX_SNAP_GAME_WIN = "snap_game_win"
TX_SNAP_GAME_BET = "snap_game_bet"
TX_DAILY_BONUS = "daily_bonus"
TX_WITHDRAWAL = "withdrawal"
TX_WITHDRAWAL_REFUND = "withdrawal_refund"
TX_ADMIN_CREDIT = "admin_credit"
TX_ADMIN_DEBIT = "admin_debit"


class TransactionModel(BaseModel):
    user_id: int
    type: str                       # one of the TX_* constants above
    amount: float                   # positive = credit, negative = debit
    balance_after: float
    description: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(IST).isoformat())
    ref_id: str = ""                # task_id / proof_id / withdrawal_id etc.

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_mongo(cls, data: dict) -> "TransactionModel":
        data = dict(data)
        data.pop("_id", None)
        data.setdefault("description", "")
        data.setdefault("ref_id", "")
        return cls(**data)
