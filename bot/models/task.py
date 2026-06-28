"""TaskModel — Pydantic v2 model for TASKHUB tasks."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


class TaskModel(BaseModel):
    id: int = 0
    task_type: str = "manual"       # "manual" | "channel"
    description: str
    guide: str = ""
    reward: float
    image: str = ""
    media_type: str = "photo"       # "photo" | "video"
    is_active: bool = True
    created_at: str = Field(default_factory=_now_ist)
    completion_count: int = 0

    # Channel task specific
    channel_id: Optional[str] = None
    channel_username: Optional[str] = None
    channel_url: Optional[str] = None
    channel_title: Optional[str] = None

    # MiniApp UI fields
    video_url: Optional[str] = None
    steps: Optional[list] = None
    color: Optional[str] = None
    color2: Optional[str] = None
    duration_text: Optional[str] = None
    expires_at: Optional[str] = None
    is_multi_reward: bool = False
    offer_url: Optional[str] = None

    # Affiliate/payout fields
    referrer_reward: float = 0.0
    completer_reward: float = 0.0
    max_completers: int = 0
    current_completers: int = 0

    class Config:
        populate_by_name = True

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_mongo(cls, data: dict) -> "TaskModel":
        data = dict(data)
        data.pop("_id", None)
        # Back-compat: older docs may not have these fields
        data.setdefault("task_type", "manual")
        data.setdefault("media_type", "photo")
        data.setdefault("is_active", True)
        data.setdefault("guide", "")
        data.setdefault("channel_id", None)
        data.setdefault("channel_username", None)
        data.setdefault("channel_url", None)
        data.setdefault("channel_title", None)
        return cls(**data)
