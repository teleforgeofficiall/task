from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MinesEngine:
    """Adaptive mines engine with intelligent bomb placement,
    progressive multiplier, and survival streak control."""

    def __init__(self):
        self._user_streaks: Dict[int, int] = {}  # user_id -> consecutive survival

    def generate_board(self, config: Dict, user_id: Optional[int] = None,
                       user_game_count: int = 0, profit_level: float = 0.0,
                       loss_streak: int = 0, effective_rtp: float = 94.0) -> Dict[str, Any]:
        """Generate a mines board with adaptive difficulty."""
        grid_size = config.get("grid_size", 9)
        base_mines = config.get("mine_count", 3)

        # Adaptive difficulty
        mine_count = self._calculate_mine_count(
            base_mines, grid_size, user_id, profit_level, loss_streak, effective_rtp, user_game_count
        )

        # Build board
        board = ["gem"] * (grid_size - mine_count) + ["mine"] * mine_count
        random.shuffle(board)

        return {
            "board": board,
            "mines": mine_count,
            "grid_size": grid_size,
        }

    def _calculate_mine_count(self, base_mines: int, grid_size: int,
                               user_id: Optional[int], profit_level: float,
                               loss_streak: int, effective_rtp: float,
                               user_game_count: int) -> int:
        """Calculate adaptive mine count based on player profile."""
        mines = base_mines

        # New user protection: fewer mines
        if user_game_count < 3:
            mines = max(1, mines - 1)

        # Profit adjustment: if user profiting, increase danger
        if profit_level > 50:
            mines += 1
        if profit_level > 200:
            mines += 1

        # Loss streak mercy
        if loss_streak >= 5:
            mines = max(1, mines - 1)
        if loss_streak >= 8:
            mines = max(1, mines - 1)

        # RTP alignment: higher RTP = slightly fewer mines
        rtp_diff = effective_rtp - 94.0
        if rtp_diff > 5:
            mines -= 1
        elif rtp_diff < -5:
            mines += 1

        # Clamp
        return max(1, min(grid_size - 1, mines))

    def get_multiplier(self, gems_found: int, total_mines: int, grid_size: int = 9) -> float:
        """Progressive multiplier based on safe tiles found."""
        if gems_found <= 0:
            return 1.0
        safe = grid_size - total_mines
        if safe <= 0 or total_mines <= 0:
            return 1.0
        # Calculate probability of surviving this many reveals
        prob = 1.0
        for i in range(gems_found):
            prob *= (safe - i) / (grid_size - i)
        # Fair multiplier with house edge
        mult = (1.0 / prob) * 0.94 if prob > 0 else 1.0
        return round(mult, 2)

    def should_tempt_cashout(self, gems_found: int, current_mult: float,
                              total_mines: int, grid_size: int) -> bool:
        """Should we create a 'temptation' moment (close call)?"""
        # The more gems found, the higher the tension
        if gems_found < 2:
            return False
        remaining = grid_size - gems_found - total_mines
        if remaining <= 0:
            return False
        # Probability of hitting a mine on next reveal
        mine_prob = total_mines / remaining
        # Create temptation when mine probability is high
        return mine_prob > 0.4 and random.random() < 0.3

    def update_streak(self, user_id: int, survived: bool) -> None:
        if survived:
            self._user_streaks[user_id] = self._user_streaks.get(user_id, 0) + 1
        else:
            self._user_streaks[user_id] = 0
