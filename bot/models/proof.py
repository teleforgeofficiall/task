"""ProofModel — Task proof submission."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

IST = timezone(timedelta(hours=5, minutes=30))


class ProofModel(BaseModel):
    id: int = 0
    user_id: int
    task_id: int
    proof_file_id: str
    file_type: str = "photo"        # "photo" | "video"
    status: str = "pending"         # "pending" | "approved" | "rejected"
    reject_reason: Optional[str] = None
    date: str = Field(default_factory=lambda: datetime.now(IST).isoformat())
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_mongo(cls, data: dict) -> "ProofModel":
        data = dict(data)
        data.pop("_id", None)
        data.setdefault("file_type", "photo")
        data.setdefault("reject_reason", None)
        data.setdefault("reviewed_by", None)
        data.setdefault("reviewed_at", None)
        return cls(**data)
