"""
bonus_manage.py — Admin controls for bonus system (enable/disable, amount, cooldown).
"""
from __future__ import annotations

import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin

logger = logging.getLogger(__name__)


async def _send_bonus_menu(
    chat_id: int,
    user_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    edit_msg_id: Optional[int] = None,
) -> None:
    """Send or edit the bonus management menu."""
    repo = Repository(await get_db())
    enabled = await repo.get_setting("bonus_enabled", True)
    amount = float(await repo.get_setting("daily_bonus", 5.0))
    cooldown = int(await repo.get_setting("bonus_cooldown_hours", 24))
    task_gate = int(await repo.get_setting("daily_bonus_task_limit", 1))

    status_icon = "🟢" if enabled else "🔴"
    status_text = "Active" if enabled else "Disabled"
    cooldown_label = f"Every {cooldown}h" if cooldown < 24 else f"Every {cooldown}h (Daily)"

    text = (
        "🎁 <b>Bonus Management</b>\n\n"
        f"{status_icon} <b>Status:</b> {status_text}\n"
        f"💰 <b>Reward Amount:</b> <code>\u20b9{amount:.2f}</code>\n"
        f"⏱ <b>Cooldown:</b> <code>{cooldown_label}</code>\n"
        f"⚙️ <b>Tasks Required:</b> <code>{task_gate}</code>\n\n"
        "Use the buttons below to manage the bonus system."
    )

    toggle_label = "🔴 Disable Bonus" if enabled else "🟢 Enable Bonus"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_label, callback_data="admin:bonus_toggle")],
        [InlineKeyboardButton("💰 Set Reward Amount", callback_data="admin:bonus_set_amount")],
        [InlineKeyboardButton("⏱ Set Cooldown", callback_data="admin:bonus_set_cooldown")],
        [InlineKeyboardButton("⚙️ Set Tasks Required", callback_data="admin:bonus_set_tasks")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ])

    bot = context.bot
    if edit_msg_id:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=edit_msg_id, parse_mode="HTML", reply_markup=kb)
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


async def admin_bonus_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    await _send_bonus_menu(query.message.chat_id, query.from_user.id, context, edit_msg_id=query.message.message_id)
    await query.answer()


async def admin_bonus_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    repo = Repository(await get_db())
    current = await repo.get_setting("bonus_enabled", True)
    await repo.update_setting("bonus_enabled", not current)
    await query.answer(f"Bonus {'enabled' if not current else 'disabled'}.")
    await admin_bonus_menu(update, context)


async def admin_bonus_set_amount_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "bonus_set_amount"
    await query.edit_message_text(
        "💰 <b>Set Bonus Reward Amount</b>\n\n"
        "Send the new reward amount (e.g. <code>10</code> for \u20b910).\n\n"
        "Use a decimal number greater than 0.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:bonus_menu")]
        ])
    )
    await query.answer()


async def admin_bonus_set_cooldown_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    repo = Repository(await get_db())
    current = int(await repo.get_setting("bonus_cooldown_hours", 24))

    text = (
        "⏱ <b>Set Bonus Cooldown</b>\n\n"
        f"Current: <code>Every {current}h</code>\n\n"
        "Select how long users must wait between claims:"
    )
    options = [3, 6, 12, 24, 48, 72]
    kb = []
    row = []
    for h in options:
        mark = " ✅" if h == current else ""
        row.append(InlineKeyboardButton(f"{h}h{mark}", callback_data=f"admin:bonus_cooldown:{h}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="admin:bonus_menu")])

    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    await query.answer()


async def admin_bonus_set_cooldown_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    hours = int(query.data.split(":")[2])
    repo = Repository(await get_db())
    await repo.update_setting("bonus_cooldown_hours", hours)
    await query.answer(f"Cooldown set to every {hours}h.")
    await admin_bonus_menu(update, context)


async def admin_bonus_set_tasks_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "bonus_set_tasks"
    await query.edit_message_text(
        "⚙️ <b>Set Tasks Required</b>\n\n"
        "Send the number of tasks a user must complete before claiming bonus (e.g. <code>1</code>).\n\n"
        "Use a whole number 0 or more.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:bonus_menu")]
        ])
    )
    await query.answer()


async def admin_bonus_handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        return
    state = context.user_data.get("admin_state")
    if state not in ("bonus_set_amount", "bonus_set_tasks"):
        return
    repo = Repository(await get_db())
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    if state == "bonus_set_amount":
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
            await repo.update_setting("daily_bonus", val)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Bonus amount set to \u20b9{val:.2f}.")
            await _send_bonus_menu(chat_id, update.effective_user.id, context)
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid amount. Send a number greater than 0.")

    elif state == "bonus_set_tasks":
        try:
            val = int(text)
            if val < 0:
                raise ValueError
            await repo.update_setting("daily_bonus_task_limit", val)
            context.user_data.pop("admin_state", None)
            await update.message.reply_text(f"✅ Tasks required set to {val}.")
            await _send_bonus_menu(chat_id, update.effective_user.id, context)
        except (ValueError, TypeError):
            await update.message.reply_text("❌ Invalid number. Send a whole number 0 or more.")


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(admin_bonus_menu, pattern="^admin:bonus_menu$"))
    application.add_handler(CallbackQueryHandler(admin_bonus_toggle, pattern="^admin:bonus_toggle$"))
    application.add_handler(CallbackQueryHandler(admin_bonus_set_amount_prompt, pattern="^admin:bonus_set_amount$"))
    application.add_handler(CallbackQueryHandler(admin_bonus_set_cooldown_menu, pattern="^admin:bonus_set_cooldown$"))
    application.add_handler(CallbackQueryHandler(admin_bonus_set_cooldown_choice, pattern=r"^admin:bonus_cooldown:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_bonus_set_tasks_prompt, pattern="^admin:bonus_set_tasks$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bonus_handle_text))
