from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CrashEngine:
    """Adaptive crash point distribution with volatility control and
    fake hot/cold streak feeling."""

    # Base distribution (cumulative) — 90% crash below 2.0x
    DISTRIBUTION = [
        (0.00, 1.20, 0.45),   # 45% crash at 1.0-1.2x
        (0.45, 2.00, 0.25),   # 25% crash at 1.2-2.0x
        (0.70, 5.00, 0.15),   # 15% crash at 2.0-5.0x
        (0.85, 15.00, 0.10),  # 10% crash at 5.0-15.0x
        (0.95, 50.00, 0.04),  # 4% crash at 15-50x
        (0.99, 100.00, 0.01), # 1% ultra rare
    ]

    def __init__(self):
        self._recent_crashes: Dict[str, list] = {}  # game -> [crash_points]

    def generate(self, config: Dict, effective_rtp: float,
                 exposure_mult_limit: float = 100.0,
                 volatility: str = "normal") -> float:
        """Generate crash point using weighted distribution."""
        # Bias the distribution based on RTP
        rtp_bias = effective_rtp / 91.0  # baseline 91%
        vol_shift = {"low": -0.05, "normal": 0.0, "high": 0.05}.get(volatility, 0.0)

        r = random.random()

        # Apply bias to shift distribution
        biased_r = r * rtp_bias + vol_shift
        biased_r = max(0.0, min(1.0, biased_r))

        for cum_prob_start, max_val, prob_width in self.DISTRIBUTION:
            cum_prob_end = cum_prob_start + prob_width
            if cum_prob_start <= biased_r < cum_prob_end:
                # Scale within the range
                within = (biased_r - cum_prob_start) / prob_width
                point = 1.0 + within * (max_val - 1.0)
                break
        else:
            point = random.uniform(1.01, 3.0)

        # Apply exposure limit
        capped = min(point, exposure_mult_limit)

        # Round to 2 decimals, minimum 1.01
        return round(max(1.01, capped), 2)

    def _get_streak_bias(self, game_key: str) -> float:
        """Returns a bias based on recent crash history."""
        recent = self._recent_crashes.get(game_key, [])[-10:]
        if len(recent) < 3:
            return 0.0
        avg = sum(recent) / len(recent)
        if avg < 2.0:
            # Recent crashes have been low — bias toward higher
            return -0.1
        elif avg > 5.0:
            # Recent crashes have been high — bias toward lower
            return 0.1
        return 0.0

    def record_crash(self, game_key: str, crash_point: float) -> None:
        if game_key not in self._recent_crashes:
            self._recent_crashes[game_key] = []
        self._recent_crashes[game_key].append(crash_point)
        # Keep only last 50
        self._recent_crashes[game_key] = self._recent_crashes[game_key][-50:]
