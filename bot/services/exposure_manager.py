from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from bot.database import Repository

logger = logging.getLogger(__name__)


class ExposureManager:
    """Global exposure protection system — prevents house bankruptcy."""

    def __init__(self, repository: Repository):
        self._repo = repository
        self._cache: Optional[Dict] = None
        self._last_load = 0.0

    async def _load_state(self) -> Dict:
        now = time.time()
        if self._cache and (now - self._last_load) < 5.0:
            return self._cache
        raw = await self._repo.get_setting("exposure_state")
        if raw and isinstance(raw, dict):
            self._cache = raw
        else:
            self._cache = {
                "daily_bet_volume": 0.0,
                "daily_payout_volume": 0.0,
                "daily_profit": 0.0,
                "current_liability": 0.0,
                "peak_liability": 0.0,
                "total_house_profit": 0.0,
                "consecutive_losing_days": 0,
                "last_reset_date": "",
                "lockdown_active": False,
            }
        self._last_load = now
        return self._cache

    async def _save_state(self, state: Dict) -> None:
        await self._repo.update_setting("exposure_state", state)
        self._cache = state
        self._last_load = time.time()

    async def record_bet(self, game: str, bet: float, payout: float) -> None:
        state = await self._load_state()
        state["daily_bet_volume"] = state.get("daily_bet_volume", 0.0) + bet
        state["daily_payout_volume"] = state.get("daily_payout_volume", 0.0) + payout
        state["current_liability"] = max(0.0, state.get("current_liability", 0.0) + payout - bet)
        state["daily_profit"] = state.get("daily_profit", 0.0) + (bet - payout)
        state["total_house_profit"] = state.get("total_house_profit", 0.0) + (bet - payout)
        if state["current_liability"] > state.get("peak_liability", 0.0):
            state["peak_liability"] = state["current_liability"]
        await self._save_state(state)

    async def get_exposure_level(self) -> Dict[str, Any]:
        """Returns current exposure level and recommended action."""
        state = await self._load_state()
        cfg_raw = await self._repo.get_setting("game_config")
        gcfg = cfg_raw.get("global", {}) if cfg_raw else {}
        exposure_cap = gcfg.get("exposure_cap", 50000)
        max_payout = gcfg.get("max_payout", 10000)

        current_liability = state.get("current_liability", 0.0)
        daily_payout = state.get("daily_payout_volume", 0.0)
        daily_profit = state.get("daily_profit", 0.0)

        # Calculate risk level 0.0–1.0
        liability_ratio = current_liability / exposure_cap if exposure_cap > 0 else 0.0
        payout_ratio = daily_payout / (exposure_cap * 0.5) if exposure_cap > 0 else 0.0
        profit_ratio = abs(min(0, daily_profit)) / (exposure_cap * 0.3) if exposure_cap > 0 else 0.0

        risk_level = min(1.0, max(liability_ratio, payout_ratio, profit_ratio))
        lockdown = state.get("lockdown_active", False)

        if lockdown or risk_level >= 0.95:
            level = "critical"
            action = "EMERGENCY_LOCKDOWN"
        elif risk_level >= 0.8:
            level = "high"
            action = "TIGHTEN"
        elif risk_level >= 0.5:
            level = "elevated"
            action = "CAUTION"
        elif risk_level >= 0.2:
            level = "normal"
            action = "MONITOR"
        else:
            level = "low"
            action = "RELAX"

        return {
            "level": level,
            "risk_score": round(risk_level, 3),
            "action": action,
            "current_liability": round(current_liability, 2),
            "daily_profit": round(daily_profit, 2),
            "daily_payout_volume": round(daily_payout, 2),
            "exposure_cap": exposure_cap,
            "max_payout": max_payout,
            "lockdown": lockdown,
        }

    async def get_rtp_adjustment(self) -> float:
        """Returns an RTP penalty (negative) or bonus (positive) based on exposure."""
        exposure = await self.get_exposure_level()
        risk = exposure["risk_score"]
        if risk < 0.2:
            return 0.0
        if risk < 0.5:
            return -1.0
        if risk < 0.8:
            return -3.0
        return -6.0

    async def get_multiplier_limit(self) -> float:
        """Returns the max multiplier allowed under current exposure."""
        exposure = await self.get_exposure_level()
        risk = exposure["risk_score"]
        if risk < 0.2:
            return 100.0
        if risk < 0.5:
            return 50.0
        if risk < 0.8:
            return 20.0
        return 5.0

    async def get_jackpot_probability_modifier(self) -> float:
        """Returns multiplier on jackpot probability (0 = no jackpots, 1 = normal)."""
        exposure = await self.get_exposure_level()
        risk = exposure["risk_score"]
        if risk < 0.3:
            return 1.0
        if risk < 0.6:
            return 0.5
        if risk < 0.8:
            return 0.2
        return 0.0

    async def reset_daily(self) -> None:
        state = await self._load_state()
        if state.get("daily_profit", 0.0) < 0:
            state["consecutive_losing_days"] = state.get("consecutive_losing_days", 0) + 1
        else:
            state["consecutive_losing_days"] = 0
        state["daily_bet_volume"] = 0.0
        state["daily_payout_volume"] = 0.0
        state["daily_profit"] = 0.0
        state["current_liability"] = 0.0
        state["last_reset_date"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone(__import__("datetime").timedelta(hours=5, minutes=30))
        ).strftime("%Y-%m-%d")
        await self._save_state(state)
