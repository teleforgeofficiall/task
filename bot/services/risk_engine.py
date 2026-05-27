from __future__ import annotations

import json
import logging
import random
import secrets
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: Dict[str, Any] = {
    "dice": {
        "rtp": 92,
        "min_bet": 1,
        "max_bet": 1000,
        "win_chance": 50,
        "payout_multiplier": 1.8,
        "cooldown_seconds": 2,
    },
    "slots": {
        "rtp": 90,
        "min_bet": 1,
        "max_bet": 1000,
        "jackpot_chance": 0.5,
        "common_multi": 2.0,
        "rare_multi": 5.0,
        "epic_multi": 15.0,
        "legendary_multi": 50.0,
        "weights": {"common": 60, "rare": 25, "epic": 10, "legendary": 5},
    },
    "mines": {
        "rtp": 94,
        "min_bet": 1,
        "max_bet": 1000,
        "mine_count": 3,
        "grid_size": 9,
    },
    "crash": {
        "rtp": 91,
        "min_bet": 1,
        "max_bet": 1000,
        "house_edge": 9,
    },
    "global": {
        "new_user_luck_rounds": 3,
        "new_user_rtp_boost": 10,
        "exposure_cap": 50000,
        "max_payout": 10000,
        "volatility": "normal",
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
    """Central RTP + Risk Engine for all casino games.

    Loads config from DB settings; caches in memory for fast reads.
    Thread-safe asyncio-friendly design — no locks needed for reads.
    """

    def __init__(self, repository=None):
        self._repo = repository
        self._cache: Optional[Dict[str, Any]] = None
        self._last_load = 0.0
        self._cache_ttl = 30.0

    async def _ensure_repo(self):
        if self._repo:
            return self._repo
        from bot.database import get_db, Repository
        db = await get_db()
        self._repo = Repository(db)
        return self._repo

    async def load_config(self) -> Dict[str, Any]:
        now = time.time()
        if self._cache and (now - self._last_load) < self._cache_ttl:
            return self._cache
        repo = await self._ensure_repo()
        raw = await repo.get_setting("game_config")
        if raw and isinstance(raw, dict):
            merged = _merge_config(_DEFAULT_CONFIG, raw)
            self._cache = merged
        else:
            self._cache = dict(_DEFAULT_CONFIG)
            await repo.update_setting("game_config", dict(_DEFAULT_CONFIG))
        self._last_load = now
        return self._cache

    async def save_config(self, config: Dict[str, Any]) -> None:
        repo = await self._ensure_repo()
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

    # ---- Stats tracking ----
    async def record_bet(self, game: str, bet: float, payout: float) -> None:
        cfg = await self.load_config()
        stats = cfg.setdefault("stats", {})
        stats["total_bets"] = stats.get("total_bets", 0) + 1
        stats["total_payouts"] = stats.get("total_payouts", 0.0) + payout
        stats["total_rake"] = stats.get("total_rake", 0.0) + (bet - payout) if bet > payout else stats.get("total_rake", 0.0)
        game_key = f"{game}_bets"
        payout_key = f"{game}_payouts"
        stats[game_key] = stats.get(game_key, 0) + 1
        stats[payout_key] = stats.get(payout_key, 0.0) + payout
        if payout > stats.get("biggest_win", 0):
            stats["biggest_win"] = payout
        if bet > payout and (bet - payout) > stats.get("biggest_loss", 0):
            stats["biggest_loss"] = bet - payout
        await self.save_config(cfg)

    async def get_stats(self) -> Dict[str, Any]:
        cfg = await self.load_config()
        return dict(cfg.get("stats", {}))

    async def get_current_rtp(self, game: str) -> float:
        stats = await self.get_stats()
        bets = stats.get(f"{game}_bets", 0)
        payouts = stats.get(f"{game}_payouts", 0.0)
        if bets < 10:
            cfg = await self.get_game_config(game)
            return float(cfg.get("rtp", 90))
        return round((payouts / (bets * 10.0)) * 100, 2) if bets else 90.0

    # ---- RTP-aware outcome helpers ----
    def _should_win(self, config_rtp: int, user_luck_boost: float = 0.0) -> bool:
        adjusted = config_rtp + user_luck_boost
        return (secrets.randbelow(10000) / 100.0) < adjusted

    def _get_user_luck_boost(self, user_game_count: int) -> float:
        gcfg = self._cache.get("global", {}) if self._cache else {}
        luck_rounds = gcfg.get("new_user_luck_rounds", 3)
        boost = gcfg.get("new_user_rtp_boost", 10)
        if user_game_count < luck_rounds:
            return boost * (1.0 - user_game_count / luck_rounds)
        return 0.0

    # ---- Per-game outcome generators ----
    def roll_dice(self, config: dict, user_game_count: int = 0, use_seeded: bool = False) -> dict:
        rtp = config.get("rtp", 92)
        boost = self._get_user_luck_boost(user_game_count)
        if use_seeded:
            roll = secrets.randbelow(6) + 1
        else:
            roll = random.randint(1, 6)
        if self._should_win(rtp, boost):
            if roll < 4:
                roll = random.randint(4, 6)
        else:
            if roll >= 4:
                roll = random.randint(1, 3)
        if roll >= 4:
            mult = config.get("payout_multiplier", 1.8)
        else:
            mult = 0.0
        return {"roll": roll, "win": roll >= 4, "multiplier": mult}

    def spin_slots(self, config: dict, user_game_count: int = 0) -> dict:
        rtp = config.get("rtp", 90)
        weights = config.get("weights", {"common": 60, "rare": 25, "epic": 10, "legendary": 5})
        boost = self._get_user_luck_boost(user_game_count)
        symbols = ["common", "rare", "epic", "legendary"]
        w = [weights.get(s, 10) for s in symbols]
        total_w = sum(w)
        norm_w = [wi / total_w for wi in w]
        reels = []
        for _ in range(3):
            if self._should_win(rtp, boost):
                r = secrets.randbelow(10000)
                cumulative = 0.0
                chosen = "common"
                for i, pw in enumerate(norm_w):
                    cumulative += pw * 10000
                    if r < cumulative:
                        chosen = symbols[i]
                        break
                reels.append(chosen)
            else:
                reels.append(random.choices(symbols, weights=w, k=1)[0])
        unique = len(set(reels))
        if unique == 1:
            sym = reels[0]
            multi_map = {"common": config.get("common_multi", 2.0),
                         "rare": config.get("rare_multi", 5.0),
                         "epic": config.get("epic_multi", 15.0),
                         "legendary": config.get("legendary_multi", 50.0)}
            mult = multi_map.get(sym, 2.0)
            jackpot = (sym == "legendary")
        elif unique == 2:
            mult = config.get("common_multi", 2.0)
            jackpot = False
        else:
            mult = 0.0
            jackpot = False
        return {"reels": reels, "win": mult > 0, "multiplier": mult, "jackpot": jackpot}

    def generate_mines(self, config: dict, mine_count: int = None, user_game_count: int = 0) -> dict:
        grid_size = config.get("grid_size", 9)
        mines = mine_count or config.get("mine_count", 3)
        if mines < 1:
            mines = 1
        if mines >= grid_size:
            mines = grid_size - 1
        board = ["gem"] * (grid_size - mines) + ["mine"] * mines
        random.shuffle(board)
        return {"board": board, "mines": mines, "grid_size": grid_size}

    def get_mines_multiplier(self, gems_found: int, total_mines: int, grid_size: int = 9) -> float:
        if gems_found <= 0:
            return 1.0
        safe = grid_size - total_mines
        if safe <= 0 or total_mines <= 0:
            return 1.0
        prob = 1.0
        for i in range(gems_found):
            prob *= (safe - i) / (grid_size - i)
        mult = (1.0 / prob) * 0.94 if prob > 0 else 1.0
        return round(mult, 2)

    def generate_crash_point(self, config: dict, user_game_count: int = 0) -> float:
        rtp = config.get("rtp", 91)
        boost = self._get_user_luck_boost(user_game_count)
        r = random.random()
        if r < 0.10:
            base = random.uniform(1.0, 1.2)
        elif r < 0.35:
            base = random.uniform(1.2, 1.5)
        elif r < 0.65:
            base = random.uniform(1.5, 2.5)
        elif r < 0.85:
            base = random.uniform(2.5, 5.0)
        elif r < 0.95:
            base = random.uniform(5.0, 10.0)
        elif r < 0.99:
            base = random.uniform(10.0, 25.0)
        else:
            base = random.uniform(25.0, 100.0)
        adjusted = base * (100.0 / rtp) * (1.0 - boost / 200.0)
        return round(max(1.01, adjusted), 2)

    # ---- Anti-abuse ----
    async def check_abuse(self, user_id: int, game: str, bet: float) -> dict:
        cfg = await self.load_config()
        gcfg = cfg.get(game, {})
        global_cfg = cfg.get("global", {})
        max_payout = global_cfg.get("max_payout", 10000)
        exposure_cap = global_cfg.get("exposure_cap", 50000)
        min_bet = gcfg.get("min_bet", 1)
        max_bet = gcfg.get("max_bet", 1000)
        if bet < min_bet:
            return {"allowed": False, "reason": f"Minimum bet is ₹{min_bet}"}
        if bet > max_bet:
            return {"allowed": False, "reason": f"Maximum bet is ₹{max_bet}"}
        if bet * 50.0 > max_payout:
            return {"allowed": False, "reason": "Bet exceeds max payout exposure"}
        repo = await self._ensure_repo()
        user = await repo.get_user(user_id)
        if user and user.fraud_score > 50:
            return {"allowed": False, "reason": "Account flagged. Contact support."}
        return {"allowed": True}

    # ---- New user luck ----
    def is_new_user_luck_active(self, game_count: int) -> bool:
        gcfg = self._cache.get("global", {}) if self._cache else {}
        return game_count < gcfg.get("new_user_luck_rounds", 3)


def _merge_config(default: dict, override: dict) -> dict:
    result = dict(default)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _merge_config(result[key], val)
        else:
            result[key] = val
    return result
