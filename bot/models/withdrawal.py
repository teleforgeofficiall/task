"""WithdrawalModel — User withdrawal requests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

IST = timezone(timedelta(hours=5, minutes=30))


class WithdrawalModel(BaseModel):
    id: int = 0
    user_id: int
    amount: float
    method: str = "upi"             # "upi" | "redeem"
    upi_id: Optional[str] = None
    redeem_code: Optional[str] = None
    status: str = "pending"         # "pending" | "paid" | "rejected"
    reject_reason: Optional[str] = None
    date: str = Field(default_factory=lambda: datetime.now(IST).isoformat())
    approved_by: Optional[int] = None
    approved_at: Optional[str] = None

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_mongo(cls, data: dict) -> "WithdrawalModel":
        data = dict(data)
        data.pop("_id", None)
        data.setdefault("reject_reason", None)
        data.setdefault("approved_by", None)
        data.setdefault("approved_at", None)
        data.setdefault("method", "upi")
        data.setdefault("up_id", None)
        data.setdefault("redeem_code", None)
        return cls(**data)
