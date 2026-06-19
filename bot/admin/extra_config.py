"""
extra_config.py — Admin controls for Streak Bonus and Snap Pick game.
"""
from __future__ import annotations

import json
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import back_to_admin

logger = logging.getLogger(__name__)


# ─── Streak Bonus Config ──────────────────────────────────────────────────

async def admin_streak_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    repo = Repository(await get_db())
    enabled = await repo.get_setting("streak_bonus_enabled", True)
    amounts = await repo.get_setting("streak_bonus_amounts", [1, 1.5, 2, 2.5, 3, 5, 10])
    amt_str = ", ".join(f"\u20b9{a}" for a in amounts)

    text = (
        "🔥 <b>Streak Bonus Configuration</b>\n\n"
        f"{'🟢' if enabled else '🔴'} <b>Status:</b> {'Active' if enabled else 'Disabled'}\n"
        f"📅 <b>7-Day Amounts:</b> <code>{amt_str}</code>\n\n"
        "Use the buttons below to configure."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Toggle Streak Bonus", callback_data="admin:streak_toggle")],
        [InlineKeyboardButton("💰 Set Streak Amounts", callback_data="admin:streak_set_amounts")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ])
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


async def admin_streak_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    repo = Repository(await get_db())
    current = await repo.get_setting("streak_bonus_enabled", True)
    await repo.update_setting("streak_bonus_enabled", not current)
    await query.answer(f"Streak bonus {'enabled' if not current else 'disabled'}.")
    await admin_streak_menu(update, context)


async def admin_streak_set_amounts_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "streak_set_amounts"
    await query.edit_message_text(
        "💰 <b>Set Streak Bonus Amounts</b>\n\n"
        "Send the 7 daily amounts as a comma-separated list.\n"
        "Example: <code>1, 1.5, 2, 2.5, 3, 5, 10</code>\n\n"
        "Day 1, Day 2, ... Day 7 (repeats).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:streak_menu")]
        ])
    )
    await query.answer()


# ─── Snap Pick Config ─────────────────────────────────────────────────────

async def admin_snap_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    repo = Repository(await get_db())
    enabled = await repo.get_setting("snap_enabled", True)
    min_bet = float(await repo.get_setting("snap_min_bet", 1.0))
    max_bet = float(await repo.get_setting("snap_max_bet", 100.0))

    text = (
        "🎲 <b>Snap Pick (Heads/Tails) Configuration</b>\n\n"
        f"{'🟢' if enabled else '🔴'} <b>Status:</b> {'Active' if enabled else 'Disabled'}\n"
        f"🔽 <b>Min Bet:</b> <code>\u20b9{min_bet:.2f}</code>\n"
        f"🔼 <b>Max Bet:</b> <code>\u20b9{max_bet:.2f}</code>\n\n"
        "Use the buttons below to configure."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Toggle Snap Pick", callback_data="admin:snap_toggle")],
        [InlineKeyboardButton("🔽 Set Min Bet", callback_data="admin:snap_set_min")],
        [InlineKeyboardButton("🔼 Set Max Bet", callback_data="admin:snap_set_max")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ])
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


async def admin_snap_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    repo = Repository(await get_db())
    current = await repo.get_setting("snap_enabled", True)
    await repo.update_setting("snap_enabled", not current)
    await query.answer(f"Snap Pick {'enabled' if not current else 'disabled'}.")
    await admin_snap_menu(update, context)


async def admin_snap_set_min_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "snap_set_min"
    await query.edit_message_text(
        "🔽 <b>Set Snap Pick Min Bet</b>\n\n"
        "Send the minimum bet amount in Rupees (e.g. <code>1</code>).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:snap_menu")]
        ])
    )
    await query.answer()


async def admin_snap_set_max_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "snap_set_max"
    await query.edit_message_text(
        "🔼 <b>Set Snap Pick Max Bet</b>\n\n"
        "Send the maximum bet amount in Rupees (e.g. <code>100</code>).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:snap_menu")]
        ])
    )
    await query.answer()


# ─── Text Input Handler ───────────────────────────────────────────────────

async def admin_extra_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or not is_admin(update.effective_user.id):
        return
    if context.user_data is None:
        return
    state = context.user_data.get("admin_state", "")
    if not state:
        return
    repo = Repository(await get_db())
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # ─── Streak handlers ───────────────────────────────────────────────
    if state == "streak_set_amounts":
        try:
            parts = [float(x.strip()) for x in text.split(",") if x.strip()]
            if len(parts) < 1:
                raise ValueError
            await repo.update_setting("streak_bonus_amounts", parts)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Streak amounts set to {len(parts)} daily values.")
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid list. Use comma-separated numbers (e.g. 1, 1.5, 2).")
        return

    # ─── Snap Pick handlers ────────────────────────────────────────────
    if state == "snap_set_min":
        try:
            val = float(text.replace(",", ""))
            if val <= 0:
                raise ValueError
            await repo.update_setting("snap_min_bet", val)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Snap Pick min bet set to \u20b9{val:.2f}.")
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid amount. Send a number greater than 0.")
        return

    if state == "snap_set_max":
        try:
            val = float(text.replace(",", ""))
            if val <= 0:
                raise ValueError
            await repo.update_setting("snap_max_bet", val)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Snap Pick max bet set to \u20b9{val:.2f}.")
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid amount. Send a number greater than 0.")
        return


def register_handlers(application) -> None:
    """Register extra config handlers."""
    # Streak
    application.add_handler(CallbackQueryHandler(admin_streak_menu, pattern="^admin:streak_menu$"))
    application.add_handler(CallbackQueryHandler(admin_streak_toggle, pattern="^admin:streak_toggle$"))
    application.add_handler(CallbackQueryHandler(admin_streak_set_amounts_prompt, pattern="^admin:streak_set_amounts$"))
    # Snap
    application.add_handler(CallbackQueryHandler(admin_snap_menu, pattern="^admin:snap_menu$"))
    application.add_handler(CallbackQueryHandler(admin_snap_toggle, pattern="^admin:snap_toggle$"))
    application.add_handler(CallbackQueryHandler(admin_snap_set_min_prompt, pattern="^admin:snap_set_min$"))
    application.add_handler(CallbackQueryHandler(admin_snap_set_max_prompt, pattern="^admin:snap_set_max$"))
    # Text handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_extra_text_handler), group=24)
