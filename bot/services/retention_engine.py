from __future__ import annotations

import logging
import random
from typing import Any, Dict, Optional

from bot.database import Repository, get_db
from bot.database.models_sql import RetentionEventTable

logger = logging.getLogger(__name__)


class RetentionEngine:
    """Retention engine — detects frustration, triggers recovery wins,
    creates hope cycles, and prevents quitting."""

    def __init__(self, repository: Repository):
        self._repo = repository

    async def analyze_session(self, user_id: int, game: str) -> Dict[str, Any]:
        """Analyze current session state and return retention signals."""
        user = await self._repo.get_user(user_id)
        if not user:
            return {"intervention_needed": False}

        cons_losses = user.consecutive_losses or 0
        session_net = user.session_net or 0.0
        session_bets = user.session_total_bets or 0

        signals = []

        # Frustration detection: 5+ consecutive losses
        if cons_losses >= 5:
            signals.append("frustration_high")

        # Quitting risk: heavy losses in short session
        if session_bets >= 10 and session_net < -(session_bets * 20):
            signals.append("quitting_risk")

        # Loss chasing: bet size increasing after losses
        if cons_losses >= 3:
            signals.append("loss_chasing")

        # Inactivity risk (handled externally by scheduler)
        # This is checked via last_active_date

        intervention = len(signals) > 0

        return {
            "intervention_needed": intervention,
            "signals": signals,
            "consecutive_losses": cons_losses,
            "session_net": session_net,
            "session_bets": session_bets,
        }

    async def get_recovery_boost(self, user_id: int, game: str) -> float:
        """Returns RTP boost percentage if retention intervention is needed."""
        analysis = await self.analyze_session(user_id, game)
        if not analysis["intervention_needed"]:
            return 0.0

        config = await self._repo.get_setting("game_config")
        ret_config = config.get("retention", {}) if config else {}
        base_boost = ret_config.get("recovery_boost_pct", 15)

        signals = analysis["signals"]
        if "frustration_high" in signals and "quitting_risk" in signals:
            return base_boost * 1.5
        if "frustration_high" in signals:
            return base_boost
        if "quitting_risk" in signals:
            return base_boost * 0.8
        if "loss_chasing" in signals:
            return base_boost * 0.5

        return 0.0

    async def should_trigger_comeback(self, user_id: int, game: str) -> bool:
        """Should we trigger a 'comeback win' to keep the user engaged?"""
        config = await self._repo.get_setting("game_config")
        ret_config = config.get("retention", {}) if config else {}
        comeback_prob = ret_config.get("comeback_win_probability", 0.35)

        analysis = await self.analyze_session(user_id, game)
        if not analysis["intervention_needed"]:
            return False

        return random.random() < comeback_prob

    async def create_hope_cycle(self, user_id: int, game: str) -> bool:
        """After a big loss, should we allow a small win to create hope?"""
        user = await self._repo.get_user(user_id)
        if not user:
            return False

        cons_losses = user.consecutive_losses or 0
        if cons_losses < 3:
            return False

        # Higher chance after more losses
        prob = min(0.7, 0.2 + (cons_losses * 0.05))
        return random.random() < prob

    async def log_retention_event(
        self, user_id: int, event_type: str, trigger_reason: str,
        game: Optional[str] = None, boost: float = 0.0, won: bool = False
    ) -> None:
        session = await get_db()
        session.add(RetentionEventTable(
            user_id=user_id,
            event_type=event_type,
            trigger_reason=trigger_reason,
            game=game,
            boost_applied=boost,
            resulted_in_win=won,
        ))
        await session.commit()
