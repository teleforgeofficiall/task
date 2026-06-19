"""
repository.py — Async PostgreSQL Repository via SQLAlchemy 2.0.

Same public interface as the original MongoDB Repository.
All methods return Pydantic models or plain dicts for full backward compatibility.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete, func, text, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models_sql import (
    UserTable, TaskTable, ProofTable, WithdrawalTable,
    TransactionTable, AdminLogTable,
    SettingTable, GameStateTable, BackupRecordTable, GameRoundTable,
    RedeemCodeTable, DeviceFingerprintTable,
)
from bot.database.session import get_database_url
from bot.models.transaction import (
    TX_ADMIN_CREDIT, TX_ADMIN_DEBIT, TransactionModel,
)
from bot.models.user import UserModel
from bot.models.task import TaskModel
from bot.models.proof import ProofModel
from bot.models.withdrawal import WithdrawalModel
from config.settings import settings

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> str:
    return datetime.now(IST).isoformat()


def _now_date_str() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


# ─── Default settings (used for seeding) ──────────────────────────────────────

# In-memory settings cache: {key: (value, timestamp)}
_settings_cache: dict[str, tuple[Any, float]] = {}
_SETTINGS_CACHE_TTL = 60.0  # seconds

_DEFAULT_SETTINGS: Dict[str, Any] = {
    "start_message": (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>Welcome to TaskHub Rewards</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "> 💸 <b>Earn Real Money</b> by completing simple tasks, playing games & inviting friends.\n\n"
        "> ✨ <i>Trusted by thousands of active users daily.</i>\n"
        "> ⚡ <i>Fast withdrawals.</i>\n"
        "> 🔒 <i>Secure & automated payout system.</i>\n"
        "> 🎁 <i>Daily rewards, bonuses & referral income available.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 <b>What You Can Do Here:</b>\n"
        "• ✅ Complete Tasks & Earn\n"
        "• 🎮 Play Games & Win Rewards\n"
        "• 👥 Invite Friends for Lifetime Commission\n"
        "• 💰 Withdraw Directly to Your Wallet\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>💬 <i>\"Small earnings become big when consistency meets opportunity.\"</i></blockquote>\n\n"
        "🔥 <b>Start now</b> and turn your free time into real rewards.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <i>Please avoid spam/fake activity. Our security system monitors all actions automatically.</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    ),
    "launch_message": (
        "💡 <b>Launch a Task</b>\n\n"
        "<blockquote>Contact admin to list your task here.</blockquote>"
    ),
    "ban_message": "🚫 <b>You have been permanently banned from using this bot.</b>",
    "min_withdraw": settings.MIN_WITHDRAW,
    "max_withdraw": settings.MAX_WITHDRAW,
    "daily_withdraw_limit": 3,
    "star_withdraw_tiers": {"15": 25.0, "30": 50.0},
    "star_withdraw_enabled": True,
    "min_star_withdraw": 1,
    "max_star_withdraw": 500,
    "refer_min_tasks": 1,
    "refer_paused": False,
    "daily_bonus": 5.0,
    "daily_bonus_task_limit": 1,
    "bonus_enabled": True,
    "bonus_cooldown_hours": 24,
    "require_contact": True,
    "fsub_channels": [],
    "custom_commands": {},
    "earn_more_items": [],
    "alerts_message": "",
    "referral_mode": settings.DEFAULT_REFERRAL_MODE,
    "fixed_referral_reward": settings.DEFAULT_FIXED_REWARD,
    "random_reward_min": settings.DEFAULT_RANDOM_MIN,
    "random_reward_max": settings.DEFAULT_RANDOM_MAX,
    "img_welcome": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_game": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_game_dice": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_game_slots": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_game_mines": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_game_crash": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_refer_new": "https://telegra.ph/file/5e2fdf0e4e93fb7cc28fe-17e0302973422b849b.jpg",
    "img_refer_paused": "https://telegra.ph/file/02790c2b0d88478d4b634-e974bcc86d6915320a.jpg",
    "img_bonus_drop": "https://telegra.ph/file/246af8dcd72ce749589fb-ddec441baa01f7ef5b.jpg",
    "img_treasure": "https://telegra.ph/file/fd64c013ba69e0d5a501c-d9b6d5828ce0edf6a8.jpg",
    "img_channel_task": "https://telegra.ph/file/8169af7a7a4a846c08aae-785a9c0e0843d922ea.jpg",
    "img_tasks_list": "https://telegra.ph/file/fd64c013ba69e0d5a501c-d9b6d5828ce0edf6a8.jpg",
    "img_leaderboard": "https://telegra.ph/file/fd64c013ba69e0d5a501c-d9b6d5828ce0edf6a8.jpg",
    "img_drop_rain": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_redeem_success": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_withdraw_redeem": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_withdraw_stars": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "img_withdraw_upi": "https://telegra.ph/file/20ab23c510650dca3405f-1aaee19ec2c221b9fb.jpg",
    "redeem_low_stock_threshold": 5,
    "redeem_stock_enabled": True,
    "redeem_method_name": "Google Redeem Code",
    "device_verification_enabled": True,
    "device_verification_url": "https://taskhub-khaki.vercel.app",
    "miniapp_url": "https://taskhub-khaki.vercel.app",
    "maintenance_mode": False,
    "admin_ids": [7371674958, 6753283646],
    "welcome_bonus_amount": 5.0,
    "ad_goal_target": 20,
    "ad_goal_reward": 1.0,
    "promo_price": 50.0,
    "promo_qr_image": "",
    "spin_enabled": True,
    "spin_cooldown_hours": 24,
    "spin_price": 0.0,
    "spin_segments": [0.5, 1, 2, 3, 5, 0, 1.5, 0.75],
    "streak_bonus_enabled": True,
    "streak_bonus_amounts": [1, 1.5, 2, 2.5, 3, 5, 10],
    "snap_enabled": True,
    "snap_min_bet": 1.0,
    "snap_max_bet": 100.0,
}

_DEFAULT_GAME_STATE: Dict[str, Any] = {
    "status": "open",
    "last_closed": "",
    "last_result": "",
    "last_open": "",
    "bets": {"heads": {}, "tails": {}},
    "auto_schedule": True,
}


def _row_to_dict(row, exclude: Optional[set] = None) -> dict:
    """Convert a SQLAlchemy model instance to a plain dict."""
    d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    if exclude:
        for k in exclude:
            d.pop(k, None)
    return d


def _user_to_model(row) -> UserModel:
    data = _row_to_dict(row)
    return UserModel(**data)


def _task_to_model(row) -> TaskModel:
    data = _row_to_dict(row)
    return TaskModel(**data)


def _proof_to_model(row) -> ProofModel:
    data = _row_to_dict(row)
    return ProofModel(**data)


def _withdrawal_to_model(row) -> WithdrawalModel:
    data = _row_to_dict(row)
    return WithdrawalModel(**data)


class Repository:
    """Async Repository — MySQL via SQLAlchemy 2.0."""

    def __init__(self, db: Optional[AsyncSession] = None):
        self._db = db
        self._user_cache: dict[int, UserModel] = {}

    async def _session(self) -> AsyncSession:
        if self._db is not None:
            return self._db
        raise RuntimeError("Repository created without a session. Use Repository(session).")

    # =========================================================================
    # INITIALISATION
    # =========================================================================

    async def ensure_defaults(self) -> None:
        """Seed default settings and game state if missing."""
        session = await self._session()

        # Migration: update old defaults to new values
        _UPGRADE_MAP: dict[str, Any] = {
            "bonus_enabled": True,
            "bonus_cooldown_hours": 24,
            "daily_bonus_task_limit": 1,
            "start_message": (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🚀 <b>Welcome to TaskHub Rewards</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "> 💸 <b>Earn Real Money</b> by completing simple tasks, playing games & inviting friends.\n\n"
                "> ✨ <i>Trusted by thousands of active users daily.</i>\n"
                "> ⚡ <i>Fast withdrawals.</i>\n"
                "> 🔒 <i>Secure & automated payout system.</i>\n"
                "> 🎁 <i>Daily rewards, bonuses & referral income available.</i>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📌 <b>What You Can Do Here:</b>\n"
                "• ✅ Complete Tasks & Earn\n"
                "• 🎮 Play Games & Win Rewards\n"
                "• 👥 Invite Friends for Lifetime Commission\n"
                "• 💰 Withdraw Directly to Your Wallet\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "<blockquote>💬 <i>\"Small earnings become big when consistency meets opportunity.\"</i></blockquote>\n\n"
                "🔥 <b>Start now</b> and turn your free time into real rewards.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "⚠️ <i>Please avoid spam/fake activity. Our security system monitors all actions automatically.</i>\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            ),
        }

        for key, value in _DEFAULT_SETTINGS.items():
            existing = await session.get(SettingTable, key)
            if existing is None:
                session.add(SettingTable(key=key, value=json.dumps(value)))

        # Apply upgrades to existing settings
        for key, value in _UPGRADE_MAP.items():
            existing = await session.get(SettingTable, key)
            if existing is not None:
                try:
                    current_val = json.loads(existing.value)
                except (json.JSONDecodeError, TypeError):
                    current_val = existing.value
                if current_val != value:
                    existing.value = json.dumps(value)

        # Migrate renamed keys
        old_snap = await session.get(SettingTable, "img_snap_pick")
        if old_snap is not None:
            new_game = await session.get(SettingTable, "img_game")
            if new_game is None:
                session.add(SettingTable(key="img_game", value=old_snap.value))
            await session.delete(old_snap)

        # Remove deprecated keys
        for deprecated in ("img_refer_success",):
            dep_row = await session.get(SettingTable, deprecated)
            if dep_row is not None:
                await session.delete(dep_row)

        # Seed per-game images if missing (copy from existing img_game)
        game_img_keys = ("img_game_dice", "img_game_slots", "img_game_mines", "img_game_crash")
        hub_img = await session.get(SettingTable, "img_game")
        hub_val = hub_img.value if hub_img else json.dumps(_DEFAULT_SETTINGS["img_game"])
        for gk in game_img_keys:
            existing = await session.get(SettingTable, gk)
            if existing is None:
                session.add(SettingTable(key=gk, value=hub_val))

        # Seed tasks_list and leaderboard images from existing img_treasure
        treasure_img = await session.get(SettingTable, "img_treasure")
        treasure_val = treasure_img.value if treasure_img else json.dumps(_DEFAULT_SETTINGS["img_treasure"])
        for nk in ("img_tasks_list", "img_leaderboard"):
            existing = await session.get(SettingTable, nk)
            if existing is None:
                session.add(SettingTable(key=nk, value=treasure_val))

        # Reset game_config to new defaults (old stored values may conflict with updated _DEFAULT_CONFIG)
        gc_row = await session.get(SettingTable, "game_config")
        if gc_row is not None:
            await session.delete(gc_row)

        gs = await session.get(GameStateTable, "state")
        if gs is None:
            session.add(GameStateTable(id="state", data=dict(_DEFAULT_GAME_STATE)))
        await session.commit()

    # =========================================================================
    # USER OPERATIONS
    # =========================================================================

    async def get_user(self, user_id: int) -> Optional[UserModel]:
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
        )
        row = row.scalar_one_or_none()
        if row:
            model = _user_to_model(row)
            self._user_cache[user_id] = model
            return model
        return None

    async def get_users_by_ids(self, user_ids: List[int]) -> List[UserModel]:
        """Fetch multiple users by their IDs. Returns list in arbitrary order."""
        if not user_ids:
            return []
        session = await self._session()
        rows = await session.execute(
            select(UserTable).where(UserTable.user_id.in_(user_ids))
        )
        rows = rows.scalars().all()
        models = [_user_to_model(r) for r in rows]
        for m in models:
            self._user_cache[m.id] = m
        return models

    async def create_user(
        self, user_id: int, username: Optional[str], first_name: str,
        referrer: Optional[int] = None,
    ) -> UserModel:
        session = await self._session()
        row = UserTable(
            user_id=user_id,
            username=username,
            first_name=first_name,
            referrer=referrer,
        )
        session.add(row)
        await session.flush()

        if referrer:
            ref_row = await session.execute(
                select(UserTable).where(UserTable.user_id == referrer)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            ref_row = ref_row.scalar_one_or_none()
            if ref_row:
                refs = list(ref_row.referrals or [])
                refs.append(user_id)
                ref_row.referrals = refs
        await session.commit()
        logger.info("Created user %d (referrer=%s)", user_id, referrer)
        return _user_to_model(row)

    async def update_user_fields(self, user_id: int, **kwargs: Any) -> None:
        self._user_cache.pop(user_id, None)
        session = await self._session()
        await session.execute(
            UserTable.__table__.update()
            .where(UserTable.user_id == int(user_id))
            .values(**kwargs)
        )
        await session.commit()

    async def touch_user(self, user_id: int) -> None:
        await self.update_user_fields(user_id, last_active_date=_now_ist())

    async def get_all_users_cursor(self, projection: Optional[dict] = None):
        """Return all users as list of dicts."""
        session = await self._session()
        rows = await session.execute(select(UserTable))
        return [_user_to_model(r) for r in rows.scalars().all()]

    async def count_users(self) -> int:
        session = await self._session()
        result = await session.execute(select(func.count(UserTable.id)))
        return result.scalar() or 0

    async def search_user(self, query: str) -> Optional[dict]:
        session = await self._session()
        if query.isdigit():
            row = await session.execute(
                select(UserTable).where(UserTable.user_id == int(query))
            )
        else:
            uname = query.lstrip("@").lower()
            row = await session.execute(
                select(UserTable).where(func.lower(UserTable.username) == uname)
            )
        row = row.scalar_one_or_none()
        if row:
            return _row_to_dict(row)
        return None

    async def get_top_earners(self, limit: int = 10) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(UserTable)
            .order_by(UserTable.lifetime_earnings.desc())
            .limit(limit)
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def get_all_user_ids(self) -> List[int]:
        session = await self._session()
        rows = await session.execute(select(UserTable.user_id))
        return [r[0] for r in rows.all()]

    async def set_drop_rain_state(self, state: dict) -> None:
        await self.update_setting("_drop_rain_state", state)

    async def get_drop_rain_state(self) -> dict:
        return await self.get_setting("_drop_rain_state", {})

    async def get_user_rank(self, user_id: int) -> int:
        u = await self.get_user(user_id)
        if not u:
            return 0
        session = await self._session()
        count = await session.execute(
            select(func.count(UserTable.id))
            .where(UserTable.lifetime_earnings > u.lifetime_earnings)
        )
        return (count.scalar() or 0) + 1

    # ─── Balance ──────────────────────────────────────────────────────────────

    async def credit_balance(
        self, user_id: int, amount: float, tx_type: str,
        description: str = "", ref_id: str = "",
    ) -> float:
        self._user_cache.pop(user_id, None)
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
            .with_for_update()
        )
        row = row.scalar_one_or_none()
        if not row:
            return 0.0
        row.balance += amount
        row.lifetime_earnings += amount
        new_balance = row.balance

        tx = TransactionTable(
            user_id=user_id, type=tx_type, amount=amount,
            balance_after=new_balance, description=description,
            ref_id=ref_id,
        )
        session.add(tx)
        await session.commit()
        return new_balance

    async def debit_balance(
        self, user_id: int, amount: float, tx_type: str,
        description: str = "", ref_id: str = "",
    ) -> float:
        self._user_cache.pop(user_id, None)
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
            .with_for_update()
        )
        row = row.scalar_one_or_none()
        if not row:
            return 0.0
        row.balance -= amount
        new_balance = row.balance

        tx = TransactionTable(
            user_id=user_id, type=tx_type, amount=-amount,
            balance_after=new_balance, description=description,
            ref_id=ref_id,
        )
        session.add(tx)
        await session.commit()
        return new_balance

    async def admin_adjust_balance(
        self, admin_id: int, user_id: int, amount: float, reason: str = "",
    ) -> float:
        tx_type = TX_ADMIN_CREDIT if amount >= 0 else TX_ADMIN_DEBIT
        if amount >= 0:
            new_bal = await self.credit_balance(user_id, abs(amount), tx_type, reason)
        else:
            new_bal = await self.debit_balance(user_id, abs(amount), tx_type, reason)
        await self.log_admin_action(
            admin_id=admin_id, action="balance_adjust",
            target=str(user_id),
            details={"amount": amount, "reason": reason, "new_balance": new_bal},
        )
        return new_bal

    # ─── Ban / Warnings ───────────────────────────────────────────────────────

    async def ban_user(self, user_id: int, admin_id: int, reason: str = "") -> None:
        await self.update_user_fields(user_id, banned=True, ban_reason=reason)
        await self.log_admin_action(admin_id, "ban", str(user_id), {"reason": reason})

    async def unban_user(self, user_id: int, admin_id: int) -> None:
        await self.update_user_fields(user_id, banned=False, ban_reason=None)
        await self.log_admin_action(admin_id, "unban", str(user_id))

    async def add_warning(self, user_id: int, admin_id: int) -> int:
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
            .with_for_update()
        )
        row = row.scalar_one_or_none()
        warnings = (row.warnings if row else 0) + 1
        await self.update_user_fields(user_id, warnings=warnings)
        if warnings >= 3:
            await self.update_user_fields(user_id, withdraw_locked=True)
        await self.log_admin_action(
            admin_id, "warn_add", str(user_id), {"new_warnings": warnings}
        )
        return warnings

    async def remove_warning(self, user_id: int, admin_id: int) -> int:
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
            .with_for_update()
        )
        row = row.scalar_one_or_none()
        warnings = max(0, (row.warnings if row else 0) - 1)
        await self.update_user_fields(user_id, warnings=warnings)
        await self.log_admin_action(
            admin_id, "warn_remove", str(user_id), {"new_warnings": warnings}
        )
        return warnings

    async def lock_withdrawal(self, user_id: int, admin_id: int) -> None:
        await self.update_user_fields(user_id, withdraw_locked=True)
        await self.log_admin_action(admin_id, "lock_withdraw", str(user_id))

    async def unlock_withdrawal(self, user_id: int, admin_id: int) -> None:
        await self.update_user_fields(user_id, withdraw_locked=False)
        await self.log_admin_action(admin_id, "unlock_withdraw", str(user_id))

    # ─── Device / Fraud ───────────────────────────────────────────────────────

    async def mark_device_verified(self, user_id: int, verified: bool) -> None:
        await self.update_user_fields(user_id, device_verified=verified)

    async def increment_fraud_score(self, user_id: int, points: int) -> int:
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
            .with_for_update()
        )
        row = row.scalar_one_or_none()
        if not row:
            return 0
        row.fraud_score += points
        score = row.fraud_score
        await session.commit()
        if score > settings.FRAUD_SCORE_THRESHOLD:
            await self.update_user_fields(user_id, is_flagged=True)
        return score

    # =========================================================================
    # TASK OPERATIONS
    # =========================================================================

    async def get_task(self, task_id: int) -> Optional[TaskModel]:
        session = await self._session()
        row = await session.get(TaskTable, int(task_id))
        if row:
            return _task_to_model(row)
        return None

    async def get_all_tasks(self) -> List[TaskModel]:
        session = await self._session()
        rows = await session.execute(
            select(TaskTable).order_by(TaskTable.id.desc())
        )
        return [_task_to_model(r) for r in rows.scalars().all()]

    async def get_active_tasks(self) -> List[TaskModel]:
        session = await self._session()
        rows = await session.execute(
            select(TaskTable)
            .where(TaskTable.is_active == True)
            .order_by(TaskTable.id.desc())
        )
        return [_task_to_model(r) for r in rows.scalars().all()]

    async def create_task(self, data: dict) -> TaskModel:
        session = await self._session()
        row = TaskTable(**data)
        session.add(row)
        await session.flush()
        new_id = row.id
        await session.commit()
            # Reload to get auto-generated id
        return await self.get_task(new_id)

    async def update_task_fields(self, task_id: int, **kwargs: Any) -> None:
        session = await self._session()
        await session.execute(
            TaskTable.__table__.update()
            .where(TaskTable.id == int(task_id))
            .values(**kwargs)
        )
        await session.commit()

    async def increment_task_completion(self, task_id: int) -> None:
        session = await self._session()
        row = await session.execute(
            select(TaskTable).where(TaskTable.id == int(task_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = row.scalar_one_or_none()
        if row:
            row.completion_count = (row.completion_count or 0) + 1
            await session.commit()

    async def toggle_task(self, task_id: int) -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        new_state = not task.is_active
        await self.update_task_fields(task_id, is_active=new_state)
        return new_state

    async def delete_task(self, task_id: int) -> None:
        session = await self._session()
        await session.execute(
            delete(TaskTable).where(TaskTable.id == int(task_id))
        )
        await session.commit()

    # =========================================================================
    # PROOF OPERATIONS
    # =========================================================================

    async def add_proof(
        self, user_id: int, task_id: int, file_id: str, file_type: str = "photo",
    ) -> ProofModel:
        session = await self._session()
        row = ProofTable(
            user_id=user_id, task_id=task_id,
            proof_file_id=file_id, file_type=file_type,
        )
        session.add(row)
        await session.flush()
        new_id = row.id
        await session.commit()
        return await self._get_proof_model(new_id)

    async def _get_proof_model(self, proof_id: int) -> Optional[ProofModel]:
        session = await self._session()
        row = await session.get(ProofTable, int(proof_id))
        if row:
            return _proof_to_model(row)
        return None

    async def get_pending_proofs(self) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(ProofTable)
            .where(ProofTable.status == "pending")
            .order_by(ProofTable.date.desc())
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def get_proof(self, proof_id: int) -> Optional[dict]:
        session = await self._session()
        row = await session.get(ProofTable, int(proof_id))
        if row:
            return _row_to_dict(row)
        return None

    async def update_proof_status(
        self, proof_id: int, status: str,
        admin_id: Optional[int] = None, reason: Optional[str] = None,
    ) -> Optional[dict]:
        session = await self._session()
        row = await session.get(ProofTable, int(proof_id))
        if not row:
            return None
        row.status = status
        if admin_id:
            row.reviewed_by = admin_id
            row.reviewed_at = _now_ist()
        if reason:
            row.reject_reason = reason
        await session.commit()
        return _row_to_dict(row)

    async def has_pending_proof(self, user_id: int, task_id: int) -> bool:
        session = await self._session()
        row = await session.execute(
            select(ProofTable.id)
            .where(
                and_(
                    ProofTable.user_id == int(user_id),
                    ProofTable.task_id == int(task_id),
                    ProofTable.status == "pending",
                )
            )
            .limit(1)
        )
        return row.first() is not None

    async def get_user_pending_proofs(self, user_id: int) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(ProofTable)
            .where(
                and_(
                    ProofTable.user_id == int(user_id),
                    ProofTable.status == "pending",
                )
            )
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    # =========================================================================
    # WITHDRAWAL OPERATIONS
    # =========================================================================

    async def add_withdrawal(
        self, user_id: int, amount: float, upi_id: Optional[str] = None,
        method: str = "upi", stars: int = 0, channel_link: str = "",
    ) -> WithdrawalModel:
        session = await self._session()
        row = WithdrawalTable(
            user_id=user_id, amount=amount,
            method=method, upi_id=upi_id,
            stars=stars, channel_link=channel_link,
        )
        session.add(row)
        await session.flush()
        new_id = row.id
        await session.commit()
        return await self._get_withdrawal_model(new_id)

    async def _get_withdrawal_model(self, wid: int) -> Optional[WithdrawalModel]:
        session = await self._session()
        row = await session.get(WithdrawalTable, int(wid))
        if row:
            return _withdrawal_to_model(row)
        return None

    async def get_pending_withdrawals(self) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(WithdrawalTable)
            .where(WithdrawalTable.status == "pending")
            .order_by(WithdrawalTable.date.desc())
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def get_withdrawal(self, wid: int) -> Optional[dict]:
        session = await self._session()
        row = await session.get(WithdrawalTable, int(wid))
        if row:
            return _row_to_dict(row)
        return None

    async def update_withdrawal_status(
        self, wid: int, status: str,
        admin_id: Optional[int] = None, reason: Optional[str] = None,
    ) -> Optional[dict]:
        session = await self._session()
        row = await session.get(WithdrawalTable, int(wid))
        if not row:
            return None
        row.status = status
        if admin_id:
            row.approved_by = admin_id
            row.approved_at = _now_ist()
        if reason:
            row.reject_reason = reason
        await session.commit()
        return _row_to_dict(row)

    async def has_pending_withdrawal(self, user_id: int) -> bool:
        session = await self._session()
        row = await session.execute(
            select(WithdrawalTable.id)
            .where(
                and_(
                    WithdrawalTable.user_id == int(user_id),
                    WithdrawalTable.status == "pending",
                )
            )
            .limit(1)
        )
        return row.first() is not None

    async def count_today_withdrawals(self, user_id: int) -> int:
        session = await self._session()
        today_start = datetime.now(IST).strftime("%Y-%m-%d")
        stmt = select(func.count(WithdrawalTable.id)).where(
            and_(
                WithdrawalTable.user_id == int(user_id),
                WithdrawalTable.date >= today_start,
            )
        )
        result = await session.execute(stmt)
        return result.scalar() or 0

    async def get_pending_redeems(self) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(WithdrawalTable)
            .where(
                and_(
                    WithdrawalTable.method == "redeem",
                    WithdrawalTable.status == "pending",
                )
            )
            .order_by(WithdrawalTable.date.desc())
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def get_pending_star_withdrawals(self) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(WithdrawalTable)
            .where(
                and_(
                    WithdrawalTable.method == "stars",
                    WithdrawalTable.status == "pending",
                )
            )
            .order_by(WithdrawalTable.date.desc())
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def update_withdrawal_redeem_code(self, wid: int, code: str) -> None:
        session = await self._session()
        row = await session.get(WithdrawalTable, int(wid))
        if row:
            row.redeem_code = code
            await session.commit()

    async def get_user_withdrawal_history(self, user_id: int, limit: int = 10) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(WithdrawalTable)
            .where(WithdrawalTable.user_id == int(user_id))
            .order_by(WithdrawalTable.date.desc())
            .limit(limit)
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    # =========================================================================
    # REDEEM CODE INVENTORY
    # =========================================================================

    async def add_redeem_codes(self, codes: List[str], amount: float) -> int:
        session = await self._session()
        count = 0
        for code in codes:
            code = code.strip()
            if not code:
                continue
            existing = await session.execute(
                select(RedeemCodeTable).where(RedeemCodeTable.code == code)
            )
            if existing.scalar_one_or_none():
                continue
            session.add(RedeemCodeTable(code=code, amount=amount))
            count += 1
        await session.commit()
        return count

    async def get_available_redeem_code(self, amount: float) -> Optional[str]:
        session = await self._session()
        row = await session.execute(
            select(RedeemCodeTable)
            .where(RedeemCodeTable.amount == amount, RedeemCodeTable.used == False)
            .limit(1)
            .with_for_update()
        )
        row = row.scalar_one_or_none()
        if not row:
            return None
        row.used = True
        row.used_by = None
        row.used_at = None
        await session.commit()
        return row.code

    async def use_redeem_code(self, code: str, user_id: int) -> bool:
        session = await self._session()
        from datetime import datetime, timezone, timedelta
        ISTt = timezone(timedelta(hours=5, minutes=30))
        row = await session.execute(
            select(RedeemCodeTable).where(
                RedeemCodeTable.code == code,
                RedeemCodeTable.used == False,
            ).with_for_update()
        )
        row = row.scalar_one_or_none()
        if not row:
            return False
        row.used = True
        row.used_by = user_id
        row.used_at = datetime.now(ISTt).isoformat()
        await session.commit()
        return True

    async def get_redeem_code_inventory(self) -> List[dict]:
        session = await self._session()
        amounts = [10, 25, 50, 100, 250, 500]
        result = []
        for amt in amounts:
            total = await session.execute(
                select(func.count(RedeemCodeTable.id))
                .where(RedeemCodeTable.amount == amt)
            )
            used = await session.execute(
                select(func.count(RedeemCodeTable.id))
                .where(RedeemCodeTable.amount == amt, RedeemCodeTable.used == True)
            )
            total = total.scalar() or 0
            used = used.scalar() or 0
            result.append({
                "amount": amt,
                "total": total,
                "used": used,
                "available": total - used,
            })
        return result

    async def get_redeem_codes_by_amount(self, amount: float, page: int = 0, per_page: int = 20) -> dict:
        session = await self._session()
        total = await session.execute(
            select(func.count(RedeemCodeTable.id))
            .where(RedeemCodeTable.amount == amount, RedeemCodeTable.used == False)
        )
        total = total.scalar() or 0
        total_pages = max(1, (total + per_page - 1) // per_page)
        rows = await session.execute(
            select(RedeemCodeTable)
            .where(RedeemCodeTable.amount == amount, RedeemCodeTable.used == False)
            .offset(page * per_page)
            .limit(per_page)
        )
        codes = [r.code for r in rows.scalars().all()]
        return {"codes": codes, "total": total, "page": page, "total_pages": total_pages}

    async def check_redeem_low_stock(self) -> List[dict]:
        session = await self._session()
        threshold = await self.get_setting("redeem_low_stock_threshold", 5)
        amounts = [10, 25, 50, 100, 250, 500]
        low = []
        for amt in amounts:
            avail = await session.execute(
                select(func.count(RedeemCodeTable.id))
                .where(RedeemCodeTable.amount == amt, RedeemCodeTable.used == False)
            )
            avail = avail.scalar() or 0
            if avail <= threshold:
                low.append({"amount": amt, "available": avail, "threshold": threshold})
        return low

    async def delete_redeem_code(self, code: str) -> bool:
        session = await self._session()
        row = await session.execute(
            select(RedeemCodeTable).where(RedeemCodeTable.code == code)
        )
        row = row.scalar_one_or_none()
        if not row:
            return False
        await session.delete(row)
        await session.commit()
        return True

    # =========================================================================
    # DEVICE VERIFICATION
    # =========================================================================

    async def store_device_fingerprint(self, device_hash: str, user_id: int) -> bool:
        session = await self._session()
        existing = await session.execute(
            select(DeviceFingerprintTable).where(DeviceFingerprintTable.device_hash == device_hash)
        )
        if existing.scalar_one_or_none():
            return False
        session.add(DeviceFingerprintTable(device_hash=device_hash, user_id=user_id))
        user_row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
        )
        user = user_row.scalar_one_or_none()
        if not user:
            await session.rollback()
            return False
        user.device_verified = True
        await session.commit()
        return True

    async def get_device_fingerprint_user(self, device_hash: str) -> Optional[int]:
        session = await self._session()
        row = await session.execute(
            select(DeviceFingerprintTable).where(DeviceFingerprintTable.device_hash == device_hash)
        )
        row = row.scalar_one_or_none()
        if row:
            return row.user_id
        return None

    # =========================================================================
    # SETTINGS OPERATIONS
    # =========================================================================

    async def get_setting(self, key: str, default: Any = None) -> Any:
        import time
        now = time.time()
        cached = _settings_cache.get(key)
        if cached is not None and (now - cached[1]) < _SETTINGS_CACHE_TTL:
            return cached[0]
        session = await self._session()
        row = await session.get(SettingTable, key)
        if row and row.value is not None:
            try:
                val = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                val = row.value
            _settings_cache[key] = (val, now)
            return val
        _settings_cache[key] = (default, now)
        return default

    async def update_setting(self, key: str, value: Any) -> None:
        _settings_cache.pop(key, None)
        session = await self._session()
        row = await session.get(SettingTable, key)
        serialized = json.dumps(value)
        if row:
            row.value = serialized
        else:
            session.add(SettingTable(key=key, value=serialized))
        await session.commit()

    async def get_all_settings(self) -> dict:
        session = await self._session()
        rows = await session.execute(select(SettingTable))
        result = {}
        for row in rows.scalars().all():
            try:
                result[row.key] = json.loads(row.value) if row.value else None
            except (json.JSONDecodeError, TypeError):
                result[row.key] = row.value
        for key, default in _DEFAULT_SETTINGS.items():
            if key not in result:
                result[key] = default
        return result

    async def get_image(self, key: str) -> str:
        val = await self.get_setting(key)
        if val:
            return val
        return _DEFAULT_SETTINGS.get(key, "")

    # ─── Earn More Items ──────────────────────────────────────────────────────

    async def get_earn_more_items(self) -> list:
        return await self.get_setting("earn_more_items", [])

    async def add_earn_more_item(self, button_name: str, msg_type: str, msg_content: str, price: float = 0.0) -> dict:
        items = await self.get_earn_more_items()
        item_id = max([i.get("id", 0) for i in items], default=0) + 1
        item = {"id": item_id, "button_name": button_name, "msg_type": msg_type, "msg_content": msg_content, "price": price}
        items.append(item)
        await self.update_setting("earn_more_items", items)
        return item

    async def update_earn_more_item(self, item_id: int, **kwargs) -> bool:
        items = await self.get_earn_more_items()
        for item in items:
            if item["id"] == item_id:
                item.update(kwargs)
                await self.update_setting("earn_more_items", items)
                return True
        return False

    async def delete_earn_more_item(self, item_id: int) -> bool:
        items = await self.get_earn_more_items()
        new_items = [i for i in items if i["id"] != item_id]
        if len(new_items) == len(items):
            return False
        await self.update_setting("earn_more_items", new_items)
        return True

    # ─── Force Subscribe ──────────────────────────────────────────────────────

    async def get_fsub_channels(self) -> List[dict]:
        return await self.get_setting("fsub_channels", [])

    async def add_fsub_channel(self, channel: dict) -> None:
        channels = await self.get_fsub_channels()
        channels.append(channel)
        await self.update_setting("fsub_channels", channels)

    async def remove_fsub_channel(self, channel_id: str) -> None:
        channels = await self.get_fsub_channels()
        channels = [c for c in channels if c.get("id") != channel_id]
        await self.update_setting("fsub_channels", channels)

    # ─── Custom Commands ──────────────────────────────────────────────────────

    async def get_custom_commands(self) -> dict:
        return await self.get_setting("custom_commands", {})

    async def set_custom_command(self, name: str, data: dict) -> None:
        cmds = await self.get_custom_commands()
        cmds[name.lower()] = data
        await self.update_setting("custom_commands", cmds)

    async def delete_custom_command(self, name: str) -> None:
        cmds = await self.get_custom_commands()
        cmds.pop(name.lower(), None)
        await self.update_setting("custom_commands", cmds)

    # =========================================================================
    # GAME STATE OPERATIONS
    # =========================================================================

    async def get_game_state(self) -> dict:
        session = await self._session()
        row = await session.get(GameStateTable, "state")
        if row:
            return dict(row.data)
        return {}

    async def update_game_state(self, **kwargs: Any) -> None:
        session = await self._session()
        row = await session.get(GameStateTable, "state")
        if row:
            row.data.update(kwargs)
        else:
            session.add(GameStateTable(id="state", data=dict(kwargs)))
        await session.commit()

    async def place_bet(self, user_id: int, side: str, amount: float) -> bool:
        session = await self._session()
        row = await session.get(GameStateTable, "state")
        if not row:
            return False
        gs = row.data
        if gs.get("status") != "open":
            return False
        uid_str = str(user_id)
        bets = gs.get("bets", {"heads": {}, "tails": {}})
        if uid_str in bets.get("heads", {}) or uid_str in bets.get("tails", {}):
            return False
        bets.setdefault(side, {})[uid_str] = amount
        gs["bets"] = bets
        row.data = gs
        await session.commit()
        return True

    async def clear_bets(self) -> None:
        await self.update_game_state(bets={"heads": {}, "tails": {}})

    # =========================================================================
    # TRANSACTION OPERATIONS
    # =========================================================================

    async def get_user_transactions(self, user_id: int, limit: int = 20) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(TransactionTable)
            .where(TransactionTable.user_id == int(user_id))
            .order_by(TransactionTable.timestamp.desc())
            .limit(limit)
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def get_transactions_summary(self) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(
                TransactionTable.type,
                func.sum(TransactionTable.amount).label("total"),
                func.count(TransactionTable.id).label("count"),
            ).group_by(TransactionTable.type)
        )
        return [
            {"_id": r.type, "total": r.total or 0.0, "count": r.count or 0}
            for r in rows.all()
        ]

    # =========================================================================
    # ADMIN LOG OPERATIONS
    # =========================================================================

    async def log_admin_action(
        self, admin_id: int, action: str,
        target: Optional[str] = None, details: Optional[dict] = None,
    ) -> None:
        session = await self._session()
        session.add(AdminLogTable(
            admin_id=admin_id, action=action,
            target=target, details=details or {},
        ))
        await session.commit()

    async def get_admin_logs(
        self, limit: int = 50, action: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> List[dict]:
        session = await self._session()
        query = select(AdminLogTable)
        if action:
            query = query.where(AdminLogTable.action == action)
        if admin_id:
            query = query.where(AdminLogTable.admin_id == admin_id)
        query = query.order_by(AdminLogTable.timestamp.desc()).limit(limit)
        rows = await session.execute(query)
        return [_row_to_dict(r) for r in rows.scalars().all()]

    # =========================================================================
    # DASHBOARD STATS
    # =========================================================================

    async def get_dashboard_stats(self) -> dict:
        now = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        week_ago = (now - timedelta(days=7)).isoformat()

        session = await self._session()
        total = await session.execute(select(func.count(UserTable.id)))
        total = total.scalar() or 0

        active = await session.execute(
            select(func.count(UserTable.id))
            .where(UserTable.last_active_date >= week_ago)
        )
        active = active.scalar() or 0

        today_joined = await session.execute(
            select(func.count(UserTable.id))
            .where(UserTable.joined_at.like(f"{today_str}%"))
        )
        today_joined = today_joined.scalar() or 0

        banned = await session.execute(
            select(func.count(UserTable.id)).where(UserTable.banned == True)
        )
        banned = banned.scalar() or 0

        suspicious = await session.execute(
            select(func.count(UserTable.id))
            .where(UserTable.fraud_score > settings.FRAUD_SCORE_THRESHOLD)
        )
        suspicious = suspicious.scalar() or 0

        pending_proofs = await session.execute(
            select(func.count(ProofTable.id))
            .where(ProofTable.status == "pending")
        )
        pending_proofs = pending_proofs.scalar() or 0

        pending_withdrawals = await session.execute(
            select(func.count(WithdrawalTable.id))
            .where(WithdrawalTable.status == "pending")
        )
        pending_withdrawals = pending_withdrawals.scalar() or 0

        paid = await session.execute(
            select(func.coalesce(func.sum(WithdrawalTable.amount), 0.0))
            .where(WithdrawalTable.status == "paid")
        )
        total_paid = round(float(paid.scalar() or 0.0), 2)

        earnings = await session.execute(
            select(func.coalesce(func.sum(UserTable.lifetime_earnings), 0.0))
        )
        total_earnings = round(float(earnings.scalar() or 0.0), 2)

        return {
            "total_users": total,
            "active_users": active,
            "today_joined": today_joined,
            "banned": banned,
            "suspicious": suspicious,
            "pending_proofs": pending_proofs,
            "pending_withdrawals": pending_withdrawals,
            "total_paid": total_paid,
            "total_earnings": total_earnings,
        }

    # =========================================================================
    # EXPORT
    # =========================================================================

    async def export_collection(
        self, collection_name: str, fmt: str = "json",
        query: Optional[dict] = None, limit: int = 500,
    ) -> Optional[str]:
        table_map = {
            "users": UserTable,
            "withdrawals": WithdrawalTable,
            "proofs": ProofTable,
            "transactions": TransactionTable,
            "admin_logs": AdminLogTable,
        }
        table = table_map.get(collection_name)
        if not table:
            return None

        session = await self._session()
        stmt = select(table).order_by(table.id.desc()).limit(limit)
        rows = await session.execute(stmt)
        docs = [_row_to_dict(r) for r in rows.scalars().all()]

        if fmt == "json":
            return json.dumps(docs, indent=2, default=str)
        elif fmt == "csv":
            if not docs:
                return ""
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=docs[0].keys())
            writer.writeheader()
            writer.writerows(docs)
            return output.getvalue()
        return str(docs)

    # =========================================================================
    # REFERRAL HELPERS
    # =========================================================================

    async def add_unclaimed_referral(self, inviter_id: int, new_user_id: int) -> None:
        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(inviter_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = row.scalar_one_or_none()
        if not row:
            return
        if new_user_id not in (row.unclaimed_referrals or []):
            unclaimed = list(row.unclaimed_referrals or [])
            unclaimed.append(new_user_id)
            row.unclaimed_referrals = unclaimed
        if new_user_id not in (row.rewarded_referrals or []):
            rewarded = list(row.rewarded_referrals or [])
            rewarded.append(new_user_id)
            row.rewarded_referrals = rewarded
        await session.commit()

    async def claim_referral_reward(self, user_id: int, ref_user_id: int) -> Optional[float]:
        u = await self.get_user(user_id)
        if not u or ref_user_id not in u.unclaimed_referrals:
            return None

        mode = await self.get_setting("referral_mode", "random")
        if mode == "fixed":
            reward = await self.get_setting("fixed_referral_reward", 0.5)
        elif mode == "smart":
            invitee = await self.get_user(ref_user_id)
            task_count = len(invitee.completed_tasks) if invitee else 0
            base = random.uniform(0.5, 2.0)
            reward = round(min(base + (task_count * 0.1), 5.0), 2)
        else:
            r = random.random()
            if r <= 0.60:
                reward = 0.5
            elif r <= 0.85:
                reward = 1.0
            elif r <= 0.95:
                reward = 2.0
            elif r <= 0.985:
                reward = 3.0
            else:
                reward = 5.0

        session = await self._session()
        row = await session.execute(
            select(UserTable).where(UserTable.user_id == int(user_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = row.scalar_one_or_none()
        if not row:
            return None
        unclaimed = list(row.unclaimed_referrals or [])
        if ref_user_id in unclaimed:
            unclaimed.remove(ref_user_id)
            row.unclaimed_referrals = unclaimed
        row.referral_earnings = (row.referral_earnings or 0.0) + reward
        await session.commit()

        await self.credit_balance(
            user_id, reward, "referral_reward",
            f"Lucky referral reward for user {ref_user_id}",
            str(ref_user_id),
        )
        return reward

    # =========================================================================
    # GAME ROUNDS / ANALYTICS
    # =========================================================================

    async def record_game_round(
        self, user_id: int, game: str, bet: float, payout: float,
        multiplier: float = 0.0, won: bool = False,
        details: Optional[dict] = None,
    ) -> None:
        session = await self._session()
        session.add(GameRoundTable(
            user_id=user_id, game=game, bet=bet, payout=payout,
            multiplier=multiplier, won=won, details=details,
        ))
        await session.commit()

    async def get_game_rounds(
        self, game: Optional[str] = None, limit: int = 100,
        user_id: Optional[int] = None,
    ) -> List[dict]:
        session = await self._session()
        stmt = select(GameRoundTable)
        if game:
            stmt = stmt.where(GameRoundTable.game == game)
        if user_id:
            stmt = stmt.where(GameRoundTable.user_id == user_id)
        stmt = stmt.order_by(GameRoundTable.timestamp.desc()).limit(limit)
        rows = await session.execute(stmt)
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def get_game_analytics(self, game: str) -> dict:
        session = await self._session()
        total_bets = await session.execute(
            select(func.count(GameRoundTable.id))
            .where(GameRoundTable.game == game)
        )
        total_bets = total_bets.scalar() or 0
        total_wins = await session.execute(
            select(func.count(GameRoundTable.id))
            .where(GameRoundTable.game == game, GameRoundTable.won == True)
        )
        total_wins = total_wins.scalar() or 0
        total_bet_amount = await session.execute(
            select(func.coalesce(func.sum(GameRoundTable.bet), 0.0))
            .where(GameRoundTable.game == game)
        )
        total_bet_amount = round(float(total_bet_amount.scalar() or 0.0), 2)
        total_payout_amount = await session.execute(
            select(func.coalesce(func.sum(GameRoundTable.payout), 0.0))
            .where(GameRoundTable.game == game)
        )
        total_payout_amount = round(float(total_payout_amount.scalar() or 0.0), 2)
        rtp = round((total_payout_amount / total_bet_amount * 100), 2) if total_bet_amount else 0.0
        return {
            "game": game,
            "total_rounds": total_bets,
            "total_wins": total_wins,
            "total_losses": total_bets - total_wins,
            "total_bet_amount": total_bet_amount,
            "total_payout_amount": total_payout_amount,
            "house_profit": round(total_bet_amount - total_payout_amount, 2),
            "rtp": rtp,
            "house_edge": round(100.0 - rtp, 2),
        }

    async def get_all_games_analytics(self) -> List[dict]:
        results = []
        for game in ("dice", "slots", "mines", "crash"):
            results.append(await self.get_game_analytics(game))
        return results

    async def record_game_bet_transaction(self, user_id: int, game: str, amount: float) -> None:
        """Deduct bet from user balance with proper tx logging."""
        await self.debit_balance(user_id, amount, f"{game}_bet", f"{game.capitalize()} bet ₹{amount:.2f}")

    async def record_game_win_transaction(self, user_id: int, game: str, payout: float, mult: float) -> None:
        """Credit win to user balance with proper tx logging."""
        await self.credit_balance(
            user_id, payout, f"{game}_win",
            f"{game.capitalize()} win @ {mult:.2f}x — ₹{payout:.2f}"
        )

    # =========================================================================
    # BACKUP RECORDS
    # =========================================================================

    async def add_backup_record(self, filename: str, file_size_bytes: Optional[int] = None,
                                 created_by: Optional[int] = None, notes: Optional[str] = None,
                                 status: str = "completed") -> dict:
        session = await self._session()
        row = BackupRecordTable(
            filename=filename, file_size_bytes=file_size_bytes,
            created_by=created_by, notes=notes, status=status,
        )
        session.add(row)
        await session.flush()
        rid = row.id
        await session.commit()
        return {"id": rid, "filename": filename, "status": status,
                "created_at": _now_ist(), "file_size_bytes": file_size_bytes}

    async def get_backup_records(self, limit: int = 20) -> List[dict]:
        session = await self._session()
        rows = await session.execute(
            select(BackupRecordTable)
            .order_by(BackupRecordTable.created_at.desc())
            .limit(limit)
        )
        return [_row_to_dict(r) for r in rows.scalars().all()]

    async def delete_backup_record(self, record_id: int) -> bool:
        session = await self._session()
        row = await session.get(BackupRecordTable, int(record_id))
        if not row:
            return False
        await session.delete(row)
        await session.commit()
        return True
