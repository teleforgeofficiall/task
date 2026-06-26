from __future__ import annotations

import json
import logging
import random
import secrets
import time
from typing import Any, Dict, Optional

from bot.database import get_db, Repository

from bot.services.user_profiler import UserProfiler
from bot.services.exposure_manager import ExposureManager
from bot.services.retention_engine import RetentionEngine
from bot.services.anti_abuse import AntiAbuseEngine
from bot.services.slot_psychology import SlotPsychologyEngine
from bot.services.crash_engine import CrashEngine
from bot.services.mines_engine import MinesEngine
from bot.services.dice_engine import DiceEngine

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "dice": {
        "rtp": 35,
        "rtp_min": 30,
        "rtp_max": 40,
        "min_bet": 1,
        "max_bet": 1000,
        "win_chance": 35,
        "payout_multiplier": 1.0,
        "cooldown_seconds": 2,
    },
    "slots": {
        "rtp": 35,
        "rtp_min": 30,
        "rtp_max": 40,
        "min_bet": 1,
        "max_bet": 1000,
        "jackpot_chance": 0.3,
        "common_multi": 1.5,
        "rare_multi": 3.0,
        "epic_multi": 8.0,
        "legendary_multi": 15.0,
        "weights": {"common": 65, "rare": 22, "epic": 8, "legendary": 5},
    },
    "mines": {
        "rtp": 35,
        "rtp_min": 30,
        "rtp_max": 40,
        "mine_count": 5,
        "grid_size": 9,
    },
    "crash": {
        "rtp": 35,
        "rtp_min": 30,
        "rtp_max": 40,
        "house_edge": 65,
    },
    "global": {
        "new_user_luck_rounds": 1,
        "new_user_rtp_boost": 3,
        "exposure_cap": 50000,
        "max_payout": 10000,
        "volatility": "normal",
    },
    "retention": {
        "recovery_boost_pct": 15,
        "comeback_win_probability": 0.35,
        "frustration_threshold": 5,
    },
    "anti_abuse": {
        "sensitivity": "normal",
        "withdrawal_review_threshold": 1000,
    },
    "jackpot": {
        "frequency": "rare",
        "max_daily": 3,
        "min_bet_for_jackpot": 10,
    },
    "stats": {
        "total_bets": 0,
        "total_payouts": 0,
        "total_rake": 0,
        "dice_bets": 0,
        "dice_payouts": 0,
        "slots_bets": 0,
        "slots_payouts": 0,
        "mines_bets": 0,
        "mines_payouts": 0,
        "crash_bets": 0,
        "crash_payouts": 0,
        "biggest_win": 0,
        "biggest_loss": 0,
    },
}


class RiskEngine:
    """Central RTP + Risk Engine — orchestrates all game systems.
    Backward compatible with all existing snapgame.py handlers."""

    def __init__(self, repository=None):
        self._repo = repository
        self._cache: Optional[Dict[str, Any]] = None
        self._last_load = 0.0
        self._cache_ttl = 30.0

        # Sub-engines (lazy init)
        self._profiler: Optional[UserProfiler] = None
        self._exposure: Optional[ExposureManager] = None
        self._retention: Optional[RetentionEngine] = None
        self._anti_abuse: Optional[AntiAbuseEngine] = None
        self._slots_psy: Optional[SlotPsychologyEngine] = None
        self._crash: Optional[CrashEngine] = None
        self._mines: Optional[MinesEngine] = None
        self._dice: Optional[DiceEngine] = None



    async def _ensure_repo(self):
        if self._repo:
            return self._repo
        db = await get_db()
        self._repo = Repository(db)
        return self._repo

    # --- Config ---

    async def load_config(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache and (now - self._last_load) < self._cache_ttl:
            return self._cache
        repo = await self._ensure_repo()
        raw = await repo.get_setting("game_config")
        if raw and isinstance(raw, dict):
            _strip_unknown_keys(raw)
            merged = _merge_config(_DEFAULT_CONFIG, raw)
            self._cache = merged
        else:
            self._cache = dict(_DEFAULT_CONFIG)
            await repo.update_setting("game_config", dict(_DEFAULT_CONFIG))
        self._last_load = now
        return self._cache

    async def save_config(self, config: Dict[str, Any]) -> None:
        repo = await self._ensure_repo()
        _strip_unknown_keys(config)
        merged = _merge_config(_DEFAULT_CONFIG, config)
        await repo.update_setting("game_config", merged)
        self._cache = merged
        self._last_load = time.time()

    async def get_game_config(self, game: str) -> Dict[str, Any]:
        cfg = await self.load_config()
        return dict(cfg.get(game, {}))

    async def get_global_config(self) -> Dict[str, Any]:
        cfg = await self.load_config()
        return dict(cfg.get("global", {}))

    # --- Sub-engine accessors ---

    def profiler(self) -> UserProfiler:
        if not self._profiler:
            self._profiler = UserProfiler(self._repo)
        return self._profiler

    def exposure(self) -> ExposureManager:
        if not self._exposure:
            repo = self._repo
            self._exposure = ExposureManager(repo)
        return self._exposure

    def retention(self) -> RetentionEngine:
        if not self._retention:
            self._retention = RetentionEngine(self._repo)
        return self._retention

    def anti_abuse(self) -> AntiAbuseEngine:
        if not self._anti_abuse:
            self._anti_abuse = AntiAbuseEngine(self._repo)
        return self._anti_abuse

    def slots_psy(self) -> SlotPsychologyEngine:
        if not self._slots_psy:
            self._slots_psy = SlotPsychologyEngine()
        return self._slots_psy

    def crash_eng(self) -> CrashEngine:
        if not self._crash:
            self._crash = CrashEngine()
        return self._crash

    def mines_eng(self) -> MinesEngine:
        if not self._mines:
            self._mines = MinesEngine()
        return self._mines

    def dice_eng(self) -> DiceEngine:
        if not self._dice:
            self._dice = DiceEngine()
        return self._dice

    # --- Effective RTP calculation ---

    async def _compute_effective_rtp(self, game: str, config: Dict,
                                      user_id: Optional[int] = None) -> Dict[str, Any]:
        """Compute the effective RTP for this game/user interaction."""
        cfg = config.get(game, {})
        base_rtp = float(cfg.get("rtp", 90))
        rtp_min = float(cfg.get("rtp_min", base_rtp - 4))
        rtp_max = float(cfg.get("rtp_max", base_rtp + 4))

        adjustments = []
        boost = 0.0

        # 1. Exposure adjustment
        exposure_adj = await self.exposure().get_rtp_adjustment()
        adjustments.append(("exposure", exposure_adj))

        # 2. User profile adjustment
        if user_id:
            profile = await self.profiler().get_profile(user_id)
            boost += profile["rtp_boost"]
            adjustments.append(("profile", profile["rtp_boost"]))

        # 3. Retention boost
        if user_id:
            ret_boost = await self.retention().get_recovery_boost(user_id, game)
            if ret_boost > 0:
                boost += ret_boost
                adjustments.append(("retention", ret_boost))

        # 4. Hope cycle
        hope = False
        if user_id:
            hope = await self.retention().create_hope_cycle(user_id, game)
            if hope:
                boost += 20.0
                adjustments.append(("hope_cycle", 20.0))

        effective = base_rtp + sum(a[1] for a in adjustments) + boost
        effective = max(rtp_min, min(rtp_max, effective))

        return {
            "effective_rtp": round(effective, 1),
            "base_rtp": base_rtp,
            "adjustments": adjustments,
            "hope_cycle": hope,
        }

    # --- Stats ---

    async def record_bet(self, game: str, bet: float, payout: float) -> None:
        cfg = await self.load_config()
        stats = cfg.setdefault("stats", {})
        stats["total_bets"] = stats.get("total_bets", 0) + 1
        stats["total_payouts"] = stats.get("total_payouts", 0.0) + payout
        rake = max(0, bet - payout)
        stats["total_rake"] = stats.get("total_rake", 0.0) + rake
        game_key = f"{game}_bets"
        payout_key = f"{game}_payouts"
        stats[game_key] = stats.get(game_key, 0) + 1
        stats[payout_key] = stats.get(payout_key, 0.0) + payout
        if payout > stats.get("biggest_win", 0):
            stats["biggest_win"] = payout
        loss = max(0, bet - payout)
        if loss > stats.get("biggest_loss", 0):
            stats["biggest_loss"] = loss
        await self.save_config(cfg)

        # Track exposure
        await self.exposure().record_bet(game, bet, payout)

    async def get_stats(self) -> Dict[str, Any]:
        cfg = await self.load_config()
        return dict(cfg.get("stats", {}))

    async def get_current_rtp(self, game: str) -> float:
        stats = await self.get_stats()
        bets = stats.get(f"{game}_bets", 0)
        payouts = stats.get(f"{game}_payouts", 0.0)
        if bets < 10:
            return float((await self.get_game_config(game)).get("rtp", 90))
        return round((payouts / (bets * 10.0)) * 100, 2) if bets else 90.0

    # --- Game outcome generators (backward compatible API) ---

    async def roll_dice(self, config: dict, user_game_count: int = 0,
                         use_seeded: bool = False, user_id: Optional[int] = None) -> dict:
        """Dice roll with smart pattern engine."""
        rtp_info = await self._compute_effective_rtp("dice", await self.load_config(), user_id)

        hope_cycle = rtp_info["hope_cycle"]
        ret_boost = sum(a[1] for a in rtp_info["adjustments"] if a[0] == "retention")

        result = self.dice_eng().roll(
            config=config,
            effective_rtp=rtp_info["effective_rtp"],
            user_id=user_id,
            user_game_count=user_game_count,
            retention_boost=ret_boost,
            hope_cycle=hope_cycle,
        )
        return result

    async def spin_slots(self, config: dict, user_game_count: int = 0,
                          user_id: Optional[int] = None,
                          force_loss: bool = False) -> dict:
        """Slots spin with psychology engine + optional W-L-L force loss."""
        cfg = await self.load_config()
        rtp_info = await self._compute_effective_rtp("slots", cfg, user_id)
        exposure_info = await self.exposure().get_exposure_level()
        jackpot_mod = await self.exposure().get_jackpot_probability_modifier()

        return self.slots_psy().spin(
            config=config,
            effective_rtp=rtp_info["effective_rtp"],
            exposure_mod=max(0.1, 1.0 - exposure_info["risk_score"]),
            user_id=user_id,
            jackpot_mod=jackpot_mod,
            force_loss=force_loss,
        )

    async def generate_mines(self, config: dict, mine_count: int = None,
                              user_game_count: int = 0,
                              user_id: Optional[int] = None,
                              profit_level: float = 0.0,
                              loss_streak: int = 0) -> dict:
        """Mines board with adaptive engine."""
        rtp_info = await self._compute_effective_rtp("mines", await self.load_config(), user_id)

        return self.mines_eng().generate_board(
            config=config,
            user_id=user_id,
            user_game_count=user_game_count,
            profit_level=profit_level,
            loss_streak=loss_streak,
            effective_rtp=rtp_info["effective_rtp"],
        )

    def get_mines_multiplier(self, gems_found: int, total_mines: int,
                              grid_size: int = 9) -> float:
        return self.mines_eng().get_multiplier(gems_found, total_mines, grid_size)

    async def generate_crash_point(self, config: dict, user_game_count: int = 0,
                                    user_id: Optional[int] = None) -> float:
        """Crash point with adaptive distribution."""
        cfg = await self.load_config()
        rtp_info = await self._compute_effective_rtp("crash", cfg, user_id)
        volatility = cfg.get("global", {}).get("volatility", "normal")
        mult_limit = await self.exposure().get_multiplier_limit()

        point = self.crash_eng().generate(
            config=config,
            effective_rtp=rtp_info["effective_rtp"],
            exposure_mult_limit=mult_limit,
            volatility=volatility,
        )
        self.crash_eng().record_crash(f"user_{user_id}" if user_id else "global", point)
        return point

    # --- Anti-abuse (backward compatible) ---

    async def check_abuse(self, user_id: int, game: str, bet: float) -> dict:
        cfg = await self.load_config()
        gcfg = cfg.get(game, {})
        global_cfg = cfg.get("global", {})
        max_payout = global_cfg.get("max_payout", 10000)
        min_bet = gcfg.get("min_bet", 1)
        max_bet = gcfg.get("max_bet", 1000)

        if bet < min_bet:
            return {"allowed": False, "reason": f"Minimum bet is \u20b9{min_bet}"}
        if bet > max_bet:
            return {"allowed": False, "reason": f"Maximum bet is \u20b9{max_bet}"}
        if bet * 50.0 > max_payout:
            return {"allowed": False, "reason": "Bet exceeds max payout exposure"}

        # Enhanced abuse check
        result = await self.anti_abuse().check_bet(user_id, game, bet)
        if not result["allowed"]:
            return {"allowed": False, "reason": result["reason"]}

        return {"allowed": True}

    async def check_abuse_withdrawal(self, user_id: int, amount: float) -> dict:
        return await self.anti_abuse().check_withdrawal(user_id, amount)

    async def is_rage_betting(self, user_id: int, current_bet: float) -> bool:
        return await self.anti_abuse().is_rage_betting(user_id, current_bet)

    # --- Session tracking ---

    async def update_session(self, user_id: int, game: str, bet: float,
                              won: bool, is_rage: bool = False) -> None:
        await self.profiler().update_session_metrics(user_id, game, bet, won, is_rage)

        # Log retention event if needed
        if won and is_rage:
            await self.retention().log_retention_event(
                user_id, "rage_recovery", "rage_bet_resulted_in_win", game=game, boost=0, won=True
            )

    async def get_profile(self, user_id: int) -> dict:
        return await self.profiler().get_profile(user_id)

    # --- New user luck ---

    def is_new_user_luck_active(self, game_count: int) -> bool:
        gcfg = self._cache.get("global", {}) if self._cache else {}
        return game_count < gcfg.get("new_user_luck_rounds", 3)

    def get_recent_dice_pattern(self, user_id: int) -> str:
        return self.dice_eng().get_recent_pattern(user_id)


def _strip_unknown_keys(config: dict) -> None:
    valid_top = set(_DEFAULT_CONFIG.keys())
    for key in list(config.keys()):
        if key not in valid_top:
            del config[key]
    for section, default_section in _DEFAULT_CONFIG.items():
        if section in config and isinstance(config[section], dict) and isinstance(default_section, dict):
            valid = set(default_section.keys())
            config[section] = {k: v for k, v in config[section].items() if k in valid}


def _merge_config(default: dict, override: dict) -> dict:
    result = dict(default)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _merge_config(result[key], val)
        else:
            result[key] = val
    return result
