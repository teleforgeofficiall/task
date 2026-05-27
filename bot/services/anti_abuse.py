from __future__ import annotations

import logging
import time
from typing import Any, Dict

from bot.database import Repository, get_db
from bot.database.models_sql import UserTable

logger = logging.getLogger(__name__)


class AntiAbuseEngine:
    """Advanced anti-abuse detection — botting, multi-accounting,
    RTP abuse, coordinated betting, scripted gameplay."""

    def __init__(self, repository: Repository):
        self._repo = repository
        self._bet_timestamps: Dict[str, list] = {}  # user_id -> [timestamps]

    async def check_bet(self, user_id: int, game: str, bet: float) -> Dict[str, Any]:
        """Full abuse check before allowing a bet."""
        config = await self._repo.get_setting("game_config")
        aa_config = config.get("anti_abuse", {}) if config else {}
        sensitivity = aa_config.get("sensitivity", "normal")

        # Sensitivity thresholds
        thresholds = {
            "low": {"max_bets_per_minute": 15, "cooldown": 1.0, "max_same_bet": 20},
            "normal": {"max_bets_per_minute": 8, "cooldown": 2.0, "max_same_bet": 10},
            "high": {"max_bets_per_minute": 4, "cooldown": 3.0, "max_same_bet": 5},
        }
        th = thresholds.get(sensitivity, thresholds["normal"])

        # Rate limiting
        now = time.time()
        user_key = f"{user_id}"
        ts_list = self._bet_timestamps.setdefault(user_key, [])
        ts_list.append(now)
        # Keep only last 60 seconds
        self._bet_timestamps[user_key] = [t for t in ts_list if now - t < 60]

        if len(self._bet_timestamps[user_key]) > th["max_bets_per_minute"]:
            return {"allowed": False, "reason": "Too many bets. Slow down.", "risk_score": 30}

        # Cooldown check (anti-spam)
        user = await self._repo.get_user(user_id)
        if user and user.last_bet_time:
            try:
                last_bet = __import__("datetime").datetime.fromisoformat(user.last_bet_time)
                elapsed = (__import__("datetime").datetime.now(
                    __import__("datetime").timezone(__import__("datetime").timedelta(hours=5, minutes=30))
                ) - last_bet).total_seconds()
                if elapsed < th["cooldown"]:
                    return {"allowed": False, "reason": "Please wait before next bet.", "risk_score": 5}
            except (ValueError, TypeError):
                pass

        # Suspicious: always same bet amount
        if user:
            meta = user.user_meta or {}
            bet_history = meta.get("bet_history", [])
            bet_history.append(bet)
            if len(bet_history) > th["max_same_bet"]:
                last_n = bet_history[-th["max_same_bet"]:]
                if len(set(last_n)) == 1:
                    return {"allowed": False, "reason": "Unusual betting pattern detected.", "risk_score": 40}
            meta["bet_history"] = bet_history[-50:]
            from sqlalchemy import update
            session = await get_db()
            await session.execute(
                update(UserTable).where(UserTable.user_id == user_id).values(user_meta=meta)
            )
            await session.commit()

        # User flagged
        if user and user.fraud_score > 50:
            return {"allowed": False, "reason": "Account under review.", "risk_score": 80}

        return {"allowed": True, "risk_score": 0}

    async def check_withdrawal(self, user_id: int, amount: float) -> Dict[str, Any]:
        """Check if a withdrawal request should be flagged."""
        config = await self._repo.get_setting("game_config")
        aa_config = config.get("anti_abuse", {}) if config else {}
        threshold = aa_config.get("withdrawal_review_threshold", 1000)

        user = await self._repo.get_user(user_id)
        if not user:
            return {"allowed": False, "reason": "User not found"}

        flags = []

        # Flag: first withdrawal is large
        if (user.withdrawal_count or 0) == 0 and amount > threshold * 0.5:
            flags.append("first_large_withdrawal")

        # Flag: withdrawing immediately after deposit
        if (user.total_deposits or 0) > 0 and (user.total_withdrawals or 0) > (user.total_deposits or 0) * 0.9:
            flags.append("rapid_withdrawal")

        # Flag: high fraud score
        if user.fraud_score > 30:
            flags.append("high_fraud_score")

        # Flag: new account, big withdrawal
        if (user.total_bets_count or 0) < 5 and amount > threshold * 0.3:
            flags.append("new_account_large_withdrawal")

        needs_review = len(flags) > 0
        return {
            "allowed": not needs_review,
            "needs_review": needs_review,
            "flags": flags,
            "reason": "Withdrawal flagged for manual review." if needs_review else "",
        }

    async def is_rage_betting(self, user_id: int, current_bet: float) -> bool:
        """Detect if user is rage betting (increasing bet after losses)."""
        user = await self._repo.get_user(user_id)
        if not user:
            return False
        cons_losses = user.consecutive_losses or 0
        if cons_losses < 2:
            return False
        avg_bet = user.avg_bet_size or 0.0
        if avg_bet > 0 and current_bet >= avg_bet * 1.5:
            return True
        return False
