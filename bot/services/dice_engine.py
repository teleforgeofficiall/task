from __future__ import annotations

import logging
import random
import secrets
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class DiceEngine:
    """Smart dice engine with psychologically engaging win/loss patterns,
    intermittent rewards, near-miss behavior, and dopamine pacing."""

    def __init__(self):
        self._user_streaks: Dict[int, List[bool]] = {}  # user_id -> [won/lost history]

    def roll(self, config: Dict, effective_rtp: float, user_id: Optional[int] = None,
             user_game_count: int = 0, retention_boost: float = 0.0,
             hope_cycle: bool = False) -> Dict[str, Any]:
        """Roll dice with smart pattern generation."""
        base_chance = config.get("win_chance", 50)
        payout_mult = config.get("payout_multiplier", 1.8)

        # Calculate adjusted win probability
        win_prob = self._calculate_win_probability(
            base_chance, effective_rtp, user_id, retention_boost, hope_cycle, user_game_count
        )

        # Determine win/loss
        won = (secrets.randbelow(10000) / 100.0) < win_prob

        # Generate roll value
        if won:
            roll = random.randint(4, 6)
        else:
            roll = random.randint(1, 3)

        # Track streak
        self._track_result(user_id, won)

        mult = payout_mult if roll >= 4 else 0.0

        return {
            "roll": roll,
            "win": won,
            "multiplier": mult if won else 0.0,
        }

    def _calculate_win_probability(self, base_chance: float, effective_rtp: float,
                                    user_id: Optional[int], retention_boost: float,
                                    hope_cycle: bool, user_game_count: int) -> float:
        """Calculate adjusted win probability based on multiple factors."""
        prob = base_chance

        # Small RTP-based adjustment (additive, not multiplicative)
        rtp_adj = (effective_rtp - base_chance) / 200.0
        prob += rtp_adj

        # Retention boost (small)
        if retention_boost > 0:
            prob += 3.0

        # Hope cycle: after big losses, small boost
        if hope_cycle:
            prob += 5.0

        # Streak-based pattern generation
        if user_id is not None:
            streak = self._user_streaks.get(user_id, [])[-10:]
            if len(streak) >= 4:
                recent_wins = sum(1 for r in streak[-4:] if r)
                if recent_wins == 4:
                    prob -= 5.0
                elif recent_wins == 0:
                    prob += 5.0
                elif recent_wins <= 1 and len(streak) >= 6:
                    prob += 3.0

        return max(3.0, min(20.0, prob))

    def _track_result(self, user_id: Optional[int], won: bool) -> None:
        if user_id is None:
            return
        if user_id not in self._user_streaks:
            self._user_streaks[user_id] = []
        self._user_streaks[user_id].append(won)
        # Keep last 50
        self._user_streaks[user_id] = self._user_streaks[user_id][-50:]

    def get_recent_pattern(self, user_id: int) -> str:
        """Return a string representation of recent pattern (for debugging)."""
        streak = self._user_streaks.get(user_id, [])[-20:]
        return "".join("W" if r else "L" for r in streak)
