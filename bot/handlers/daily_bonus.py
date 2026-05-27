"""
daily_bonus.py — Daily login bonus claims with task gates and configurable cooldown.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import daily_bonus_keyboard
from bot.utils import edit_or_reply, format_currency

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _ts_now() -> str:
    return datetime.now(IST).isoformat()


def _parse_last_bonus(raw: str) -> Optional[datetime]:
    """Parse last_daily_bonus; handles both ISO and old YYYY-MM-DD format."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        pass
    # Try old YYYY-MM-DD format
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=IST)
    except (ValueError, TypeError):
        return None


async def _can_claim(user, repo: Repository) -> tuple[bool, str]:
    """Returns (can_claim, reason_if_blocked)."""
    enabled = await repo.get_setting("bonus_enabled", True)
    if not enabled:
        return False, "disabled"

    cooldown_hours = int(await repo.get_setting("bonus_cooldown_hours", 24))
    last_dt = _parse_last_bonus(user.last_daily_bonus)

    if last_dt is not None:
        elapsed = datetime.now(IST) - last_dt
        if elapsed.total_seconds() < cooldown_hours * 3600:
            remaining = timedelta(hours=cooldown_hours) - elapsed
            hours, rem = divmod(int(remaining.total_seconds()), 3600)
            mins = rem // 60
            return False, f"cooldown:{hours}h {mins}m"

    task_gate = int(await repo.get_setting("daily_bonus_task_limit", 1))
    if len(user.completed_tasks) < task_gate:
        return False, f"tasks:{len(user.completed_tasks)}/{task_gate}"

    return True, "ok"


async def daily_bonus_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the daily bonus dashboard."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("❌ User profile not found.")
        return

    bonus_val = await repository.get_setting("daily_bonus", 5.0)
    task_gate = int(await repository.get_setting("daily_bonus_task_limit", 1))
    cooldown_hours = int(await repository.get_setting("bonus_cooldown_hours", 24))
    enabled = await repository.get_setting("bonus_enabled", True)

    can_claim_flag, reason = await _can_claim(user, repository)

    status_text = ""
    can_claim = False

    if not enabled:
        status_text = "🔴 <b>Daily Bonus is currently disabled by admin.</b>\nCheck back later."
    elif reason.startswith("cooldown:"):
        remain = reason.split(":", 1)[1]
        status_text = (
            f"⏳ <b>Bonus on cooldown</b>\n"
            f"Come back in <b>{remain}</b> to claim again."
        )
    elif reason.startswith("tasks:"):
        prog = reason.split(":", 1)[1]
        status_text = (
            f"🔒 <b>Daily Bonus Locked</b>\n\n"
            f"Tasks completed: <code>{prog}</code>\n"
            f"Complete at least <code>{task_gate}</code> task(s) from the <b>Tasks</b> menu to unlock."
        )
    else:
        status_text = "🎁 <b>Your daily bonus is ready!</b>\nTap the button below to claim your free reward."
        can_claim = True

    cooldown_label = f"Every {cooldown_hours}h" if cooldown_hours < 24 else "Daily"

    text = (
        f"🎁 <b>Daily Bonus</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Earn free rewards regularly just by staying active.\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Reward:</b> <code>{format_currency(bonus_val)}</code>\n"
        f"⏱ <b>Cooldown:</b> <code>{cooldown_label}</code>\n"
        f"⚙️ <b>Tasks Required:</b> <code>{task_gate}</code>\n\n"
        f"────────────────────\n"
        f"{status_text}\n"
        f"────────────────────"
    )

    banner_url = await repository.get_image("img_bonus_drop")
    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=daily_bonus_keyboard(can_claim),
        image_url=banner_url
    )


async def daily_bonus_claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process daily bonus claim."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        return

    can_claim_flag, reason = await _can_claim(user, repository)
    if not can_claim_flag:
        if reason == "disabled":
            await query.answer("❌ Daily bonus is currently disabled by admin.", show_alert=True)
        elif reason.startswith("cooldown:"):
            await query.answer(f"⏳ Bonus on cooldown. Please wait.", show_alert=True)
        elif reason.startswith("tasks:"):
            prog = reason.split(":", 1)[1]
            await query.answer(f"❌ Complete {prog} task(s) first.", show_alert=True)
        else:
            await query.answer("❌ Cannot claim at this time.", show_alert=True)
        return

    bonus_val = await repository.get_setting("daily_bonus", 5.0)
    if bonus_val <= 0:
        await query.answer("❌ Daily bonus amount is not configured.", show_alert=True)
        return

    # Claim bonus
    await repository.credit_balance(
        user_id=user_id,
        amount=bonus_val,
        tx_type="daily_bonus",
        description="Daily login bonus reward"
    )

    # Store ISO timestamp for cooldown tracking
    await repository.update_user_fields(user_id, last_daily_bonus=_ts_now())

    await query.answer(f"🎁 Claimed successfully! Credited {format_currency(bonus_val)}.", show_alert=True)

    await daily_bonus_menu_handler(update, context)


def register_handlers(application) -> None:
    """Register daily bonus handlers."""
    application.add_handler(CallbackQueryHandler(daily_bonus_menu_handler, pattern="^menu:daily_bonus$"))
    application.add_handler(CallbackQueryHandler(daily_bonus_claim_handler, pattern="^bonus:claim$"))
