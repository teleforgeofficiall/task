from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.utils import escape_html

logger = logging.getLogger(__name__)


async def alerts_manager_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())
    alerts_message = await repository.get_setting("alerts_message", "")

    text = (
        "🔔 <b>Alerts Manager</b>\n\n"
        "Set a notification message that users will see when they tap <b>Alerts</b>.\n"
        "After the user taps <b>Mark as Read</b>, the alert disappears until a new one is set.\n\n"
        f"<b>Current Alert:</b>\n"
        f"{escape_html(alerts_message) if alerts_message else '<i>No alert set</i>'}"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Set Alert Message", callback_data="admin:alerts_set_msg")],
        [InlineKeyboardButton("❌ Clear Alert", callback_data="admin:alerts_clear")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ]

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def alerts_set_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_alerts_msg"

    await query.edit_message_text(
        text="✏️ <b>Set Alert Message</b>\n\nPlease send the alert message text users will see when they tap <b>Alerts</b>.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:alerts_mgmt")]
        ]),
        parse_mode="HTML",
    )
    await query.answer()


async def alerts_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    await repository.update_setting("alerts_message", "")

    await query.answer("Alert cleared!")
    query.data = "admin:alerts_mgmt"
    await alerts_manager_handler(update, context)


async def alerts_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_state = context.user_data.get("admin_state", "")
    if admin_state != "awaiting_alerts_msg":
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text_html or msg.text
    repository = Repository(await get_db())
    await repository.update_setting("alerts_message", text)
    context.user_data.pop("admin_state", None)

    await msg.reply_text("✅ Alert message saved! Users will see this when they tap Alerts.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="admin:alerts_mgmt")]
    ]), parse_mode="HTML")


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(alerts_manager_handler, pattern="^admin:alerts_mgmt$"))
    application.add_handler(CallbackQueryHandler(alerts_set_msg, pattern="^admin:alerts_set_msg$"))
    application.add_handler(CallbackQueryHandler(alerts_clear, pattern="^admin:alerts_clear$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, alerts_text_handler), group=21)
