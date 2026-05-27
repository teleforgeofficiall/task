from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from bot.database import get_db, Repository
from bot.database.models_sql import UserTable

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

PROFILE_TYPES = {
    "new_user": {"rtp_boost": 8, "volatility_shift": -0.1, "label": "New User"},
    "casual": {"rtp_boost": 2, "volatility_shift": 0.0, "label": "Casual Player"},
    "whale": {"rtp_boost": -3, "volatility_shift": 0.2, "label": "Whale"},
    "high_risk": {"rtp_boost": -5, "volatility_shift": 0.3, "label": "High Risk"},
    "grinder": {"rtp_boost": 1, "volatility_shift": -0.05, "label": "Grinder"},
    "profit_hunter": {"rtp_boost": -4, "volatility_shift": 0.15, "label": "Profit Hunter"},
    "retention_risk": {"rtp_boost": 10, "volatility_shift": -0.2, "label": "Retention Risk"},
    "bonus_abuser": {"rtp_boost": -8, "volatility_shift": 0.4, "label": "Bonus Abuser"},
    "suspicious": {"rtp_boost": -10, "volatility_shift": 0.5, "label": "Suspicious"},
}


class UserProfiler:
    """User profiling engine — tracks behavior and computes profile type."""

    def __init__(self, repository: Repository):
        self._repo = repository

    async def get_profile(self, user_id: int) -> Dict[str, Any]:
        """Get or compute the current profile for a user."""
        user = await self._repo.get_user(user_id)
        if not user:
            return {"type": "new_user", "rtp_boost": 8, "volatility_shift": -0.1}

        meta = user.user_meta or {}

        # Auto-detect if no profile yet
        profile_type = meta.get("profile_type")
        if not profile_type:
            profile_type = self._detect_profile(user, meta)
            meta["profile_type"] = profile_type
            if not user.user_meta:
                from bot.database.models_sql import UserTable
                from sqlalchemy import update
                session = await get_db()
                await session.execute(
                    update(UserTable).where(UserTable.user_id == user_id).values(user_meta=meta)
                )
                await session.commit()

        profile = PROFILE_TYPES.get(profile_type, PROFILE_TYPES["casual"])
        return {
            "type": profile_type,
            "rtp_boost": profile["rtp_boost"],
            "volatility_shift": profile["volatility_shift"],
            "label": profile["label"],
            "meta": meta,
        }

    def _detect_profile(self, user, meta: Dict) -> str:
        """Determine user profile type from behavior data."""
        total_bets = user.total_bets_count or 0
        total_deposits = user.total_deposits or 0.0
        total_withdrawals = user.total_withdrawals or 0.0
        net = user.net_profit or 0.0
        avg_bet = user.avg_bet_size or 0.0
        consecutive_losses = user.consecutive_losses or 0
        fraud_score = user.fraud_score or 0
        rage_bets = user.rage_bet_count or 0

        # Suspicious
        if fraud_score > 30:
            return "suspicious"

        # Bonus abuser
        if meta.get("bonus_claim_count", 0) > 20 and total_deposits < 50:
            return "bonus_abuser"

        # New user
        if total_bets < 10:
            return "new_user"

        # Retention risk: heavy losses, possible quitting
        if consecutive_losses >= 8:
            return "retention_risk"

        # Whale: big deposits, big bets
        if total_deposits > 5000 or avg_bet > 200:
            return "whale"

        # Profit hunter: consistently withdrawing, playing only winning games
        if total_withdrawals > total_deposits * 0.7 and net > 0:
            return "profit_hunter"

        # High risk: rage betting, loss chasing
        if rage_bets > 5 or (consecutive_losses >= 5 and avg_bet > 50):
            return "high_risk"

        # Grinder: many small bets, consistent play
        if total_bets > 100 and avg_bet < 20:
            return "grinder"

        return "casual"

    async def update_session_metrics(
        self, user_id: int, game: str, bet: float, won: bool, is_rage: bool = False
    ) -> None:
        """Update user session tracking fields after each bet."""
        from sqlalchemy import update
        from bot.database.models_sql import UserTable
        session = await get_db()

        user = await self._repo.get_user(user_id)
        if not user:
            return

        now_str = datetime.now(IST).isoformat()

        updates = {
            "total_bets_count": (user.total_bets_count or 0) + 1,
            "last_game_played": game,
            "last_bet_time": now_str,
        }

        if won:
            updates["total_wins_count"] = (user.total_wins_count or 0) + 1
            updates["session_total_wins"] = (user.session_total_wins or 0) + 1
            updates["session_total_losses"] = 0
            updates["consecutive_wins"] = (user.consecutive_wins or 0) + 1
            updates["consecutive_losses"] = 0
            updates["session_net"] = (user.session_net or 0.0) + bet
            if user.consecutive_wins and user.consecutive_wins + 1 > (user.longest_win_streak or 0):
                updates["longest_win_streak"] = (user.consecutive_wins or 0) + 1
        else:
            updates["consecutive_losses"] = (user.consecutive_losses or 0) + 1
            updates["consecutive_wins"] = 0
            updates["session_total_losses"] = (user.session_total_losses or 0) + 1
            updates["session_net"] = (user.session_net or 0.0) - bet
            if user.consecutive_losses and user.consecutive_losses + 1 > (user.longest_loss_streak or 0):
                updates["longest_loss_streak"] = (user.consecutive_losses or 0) + 1

        if is_rage:
            updates["rage_bet_count"] = (user.rage_bet_count or 0) + 1

        # Compute avg bet size
        old_total_bets = user.total_bets_count or 0
        old_avg = user.avg_bet_size or 0.0
        if old_total_bets > 0:
            new_avg = ((old_avg * old_total_bets) + bet) / (old_total_bets + 1)
        else:
            new_avg = bet
        updates["avg_bet_size"] = round(new_avg, 2)

        # Start session if first bet
        if not user.current_session_start:
            updates["current_session_start"] = now_str

        await session.execute(
            update(UserTable).where(UserTable.user_id == user_id).values(**updates)
        )
        await session.commit()

    async def record_deposit(self, user_id: int, amount: float) -> None:
        from sqlalchemy import update
        from bot.database.models_sql import UserTable
        session = await get_db()
        user = await self._repo.get_user(user_id)
        if not user:
            return
        await session.execute(
            update(UserTable)
            .where(UserTable.user_id == user_id)
            .values(
                total_deposits=(user.total_deposits or 0.0) + amount,
                net_profit=(user.net_profit or 0.0) - amount,
            )
        )
        await session.commit()

    async def record_withdrawal(self, user_id: int, amount: float) -> None:
        from sqlalchemy import update
        from bot.database.models_sql import UserTable
        session = await get_db()
        user = await self._repo.get_user(user_id)
        if not user:
            return
        await session.execute(
            update(UserTable)
            .where(UserTable.user_id == user_id)
            .values(
                total_withdrawals=(user.total_withdrawals or 0.0) + amount,
                net_profit=(user.net_profit or 0.0) + amount,
            )
        )
        await session.commit()
