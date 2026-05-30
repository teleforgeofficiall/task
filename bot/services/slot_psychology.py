from __future__ import annotations

import logging
import random
import secrets
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYMBOLS = ["common", "rare", "epic", "legendary"]
EMOJI_MAP = {"common": "🍒", "rare": "🔔", "epic": "⭐", "legendary": "👑"}

# Default weights per volatility mode
VOLATILITY_WEIGHTS = {
    "low": {"common": 70, "rare": 20, "epic": 8, "legendary": 2},
    "normal": {"common": 60, "rare": 25, "epic": 10, "legendary": 5},
    "high": {"common": 45, "rare": 30, "epic": 15, "legendary": 10},
}


class SlotPsychologyEngine:
    """Psychology-driven slot machine with near-misses, weighted reels,
    adaptive jackpot control, and fake momentum."""

    def __init__(self):
        self._momentum: Dict[str, float] = {}  # user_id -> momentum factor

    def spin(self, config: Dict, effective_rtp: float, exposure_mod: float = 1.0,
             user_id: Optional[int] = None, jackpot_mod: float = 1.0,
             force_loss: bool = False) -> Dict[str, Any]:
        """Spin the slot with full psychology system."""
        weights = config.get("weights", VOLATILITY_WEIGHTS["normal"])
        w = [weights.get(s, 10) for s in SYMBOLS]

        # Apply jackpot probability modifier
        legendary_idx = SYMBOLS.index("legendary")
        w[legendary_idx] = max(1, int(w[legendary_idx] * jackpot_mod))

        # Apply momentum for this user
        momentum = self._get_momentum(user_id)
        if momentum > 0:
            # Shift weight slightly toward wins
            w[0] = max(1, int(w[0] * (1.0 - momentum * 0.2)))
            w[1] = int(w[1] * (1.0 + momentum * 0.1))

        total_w = sum(w)
        norm_w = [wi / total_w for wi in w]

        # Generate 3 reels
        reels = []
        if force_loss:
            reels = self._generate_all_loss(norm_w)
        elif random.random() < (effective_rtp / 100.0):
            reels = self._generate_winning_reels(norm_w, effective_rtp)
        else:
            reels = self._generate_losing_reels(norm_w, effective_rtp)

        # Check for near-miss condition
        near_miss = self._is_near_miss(reels)

        # Determine result
        unique = len(set(reels))
        if unique == 1:
            sym = reels[0]
            multi_map = {
                "common": config.get("common_multi", 2.0),
                "rare": config.get("rare_multi", 5.0),
                "epic": config.get("epic_multi", 15.0),
                "legendary": config.get("legendary_multi", 50.0),
            }
            mult = multi_map.get(sym, 2.0)
            is_jackpot = (sym == "legendary")
        elif unique == 2:
            mult = config.get("common_multi", 2.0)
            is_jackpot = False
        else:
            mult = 0.0
            is_jackpot = False

        # Update momentum
        if mult > 0:
            self._momentum[str(user_id) if user_id else ""] = max(0, momentum - 0.1)
        else:
            self._momentum[str(user_id) if user_id else ""] = min(0.5, momentum + 0.05)

        return {
            "reels": reels,
            "display": " | ".join(EMOJI_MAP.get(s, "❓") for s in reels),
            "win": mult > 0,
            "multiplier": mult,
            "jackpot": is_jackpot,
            "near_miss": near_miss,
        }

    def _generate_winning_reels(self, weights: List[float], rtp: float) -> List[str]:
        """Generate reels that result in a win."""
        # Decide what kind of win
        roll = random.random()
        if roll < 0.7:
            # 2-match win (common)
            sym = random.choices(SYMBOLS, weights=weights, k=1)[0]
            other = random.choice([s for s in SYMBOLS if s != sym])
            return [sym, sym, other]
        elif roll < 0.95:
            # 3-match common/rare
            sym = random.choices(SYMBOLS[:-1], weights=weights[:-1], k=1)[0]
            return [sym, sym, sym]
        else:
            # Rare jackpot attempt
            sym = random.choices(SYMBOLS, weights=weights, k=1)[0]
            return [sym, sym, sym]

    def _generate_losing_reels(self, weights: List[float], rtp: float) -> List[str]:
        """Generate reels that result in a loss, with occasional near-misses."""
        roll = random.random()
        if roll < 0.15:
            # Near miss: two legendaries
            return ["legendary", "legendary", random.choices(SYMBOLS[:-1], weights=weights[:-1], k=1)[0]]
        elif roll < 0.30:
            # Near miss: two epics
            return ["epic", "epic", random.choices(["common", "rare"], weights=[60, 40], k=1)[0]]
        else:
            # Full loss: all different
            return random.choices(SYMBOLS, weights=weights, k=3)

    def _generate_all_loss(self, weights: List[float]) -> List[str]:
        """Generate 3 different symbols — guaranteed loss (no 2-match)."""
        syms = random.choices(SYMBOLS, weights=weights, k=3)
        while len(set(syms)) < 3:
            syms = random.choices(SYMBOLS, weights=weights, k=3)
        return syms

    def _is_near_miss(self, reels: List[str]) -> bool:
        """Detect near-miss patterns (two high-value symbols)."""
        counts = {}
        for s in reels:
            counts[s] = counts.get(s, 0) + 1
        for sym, count in counts.items():
            if count == 2 and sym in ("epic", "legendary"):
                return True
        return False

    def _get_momentum(self, user_id: Optional[int]) -> float:
        if user_id is None:
            return 0.0
        return self._momentum.get(str(user_id), 0.0)

    def reset_momentum(self, user_id: int) -> None:
        self._momentum.pop(str(user_id), None)
