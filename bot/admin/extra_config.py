"""
extra_config.py — Admin controls for Spin/Wheel, Streak Bonus, and Snap Pick game.
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


# ─── Spin & Win Config ────────────────────────────────────────────────────

async def admin_spin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    repo = Repository(await get_db())
    enabled = await repo.get_setting("spin_enabled", True)
    cooldown = int(await repo.get_setting("spin_cooldown_hours", 24))
    price = float(await repo.get_setting("spin_price", 0.0))
    segments = await repo.get_setting("spin_segments", [0.5, 1, 2, 3, 5, 0, 1.5, 0.75])
    seg_str = ", ".join(f"\u20b9{s}" for s in segments)

    text = (
        "🎡 <b>Spin & Win Configuration</b>\n\n"
        f"{'🟢' if enabled else '🔴'} <b>Status:</b> {'Active' if enabled else 'Disabled'}\n"
        f"⏱ <b>Cooldown:</b> <code>{cooldown}h</code>\n"
        f"💰 <b>Spin Price:</b> <code>\u20b9{price:.2f}</code>\n"
        f"🎯 <b>Reward Segments:</b> <code>{seg_str}</code>\n\n"
        "Use the buttons below to configure."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Toggle Spin", callback_data="admin:spin_toggle")],
        [InlineKeyboardButton("⏱ Set Cooldown (hours)", callback_data="admin:spin_set_cooldown")],
        [InlineKeyboardButton("💰 Set Spin Price", callback_data="admin:spin_set_price")],
        [InlineKeyboardButton("🎯 Set Reward Segments", callback_data="admin:spin_set_segments")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ])
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


async def admin_spin_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    repo = Repository(await get_db())
    current = await repo.get_setting("spin_enabled", True)
    await repo.update_setting("spin_enabled", not current)
    await query.answer(f"Spin {'enabled' if not current else 'disabled'}.")
    await admin_spin_menu(update, context)


async def admin_spin_set_cooldown_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "spin_set_cooldown"
    await query.edit_message_text(
        "⏱ <b>Set Spin Cooldown</b>\n\n"
        "Send the cooldown in hours (e.g. <code>24</code> for once per day).\n"
        "Use a whole number greater than 0.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:spin_menu")]
        ])
    )
    await query.answer()


async def admin_spin_set_price_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "spin_set_price"
    await query.edit_message_text(
        "💰 <b>Set Spin Price</b>\n\n"
        "Send the price per spin in Rupees (e.g. <code>0</code> for free, <code>2</code> for \u20b92).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:spin_menu")]
        ])
    )
    await query.answer()


async def admin_spin_set_segments_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "spin_set_segments"
    await query.edit_message_text(
        "🎯 <b>Set Spin Reward Segments</b>\n\n"
        "Send the reward amounts as a comma-separated list.\n"
        "Example: <code>0.5, 1, 2, 3, 5, 0, 1.5, 0.75</code>\n\n"
        "Each value is a possible reward the user can win.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:spin_menu")]
        ])
    )
    await query.answer()


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

    # ─── Spin handlers ─────────────────────────────────────────────────
    if state == "spin_set_cooldown":
        try:
            val = int(text)
            if val <= 0:
                raise ValueError
            await repo.update_setting("spin_cooldown_hours", val)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Spin cooldown set to {val}h.")
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid number. Send a whole number greater than 0.")
        return

    if state == "spin_set_price":
        try:
            val = float(text.replace(",", ""))
            if val < 0:
                raise ValueError
            await repo.update_setting("spin_price", val)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Spin price set to \u20b9{val:.2f}.")
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid amount. Send a number 0 or more.")
        return

    if state == "spin_set_segments":
        try:
            parts = [float(x.strip()) for x in text.split(",") if x.strip()]
            if len(parts) < 2:
                raise ValueError
            await repo.update_setting("spin_segments", parts)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Spin segments set to {len(parts)} values.")
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid list. Use comma-separated numbers (e.g. 0.5, 1, 2).")
        return

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
    # Spin
    application.add_handler(CallbackQueryHandler(admin_spin_menu, pattern="^admin:spin_menu$"))
    application.add_handler(CallbackQueryHandler(admin_spin_toggle, pattern="^admin:spin_toggle$"))
    application.add_handler(CallbackQueryHandler(admin_spin_set_cooldown_prompt, pattern="^admin:spin_set_cooldown$"))
    application.add_handler(CallbackQueryHandler(admin_spin_set_price_prompt, pattern="^admin:spin_set_price$"))
    application.add_handler(CallbackQueryHandler(admin_spin_set_segments_prompt, pattern="^admin:spin_set_segments$"))
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
