from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import back_to_menu_keyboard
from bot.utils import edit_or_reply

logger = logging.getLogger(__name__)


async def alerts_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())

    # Check if user already cleared the current alert
    user_data_key = "alert_cleared"
    if context.user_data.get(user_data_key):
        await edit_or_reply(
            update=update,
            context=context,
            text="🔔 <b>No Alerts</b>\n\nYou have no recent notifications.",
            reply_markup=back_to_menu_keyboard()
        )
        return

    alerts_message = await repository.get_setting("alerts_message", "")

    if not alerts_message:
        text = "🔔 <b>No Alerts</b>\n\nYou have no recent notifications."
        reply_markup = back_to_menu_keyboard()
    else:
        text = f"🔔 <b>Alert</b>\n\n{alerts_message}"
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Mark as Read", callback_data="alerts:mark_read")],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")],
        ])

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=reply_markup,
    )


async def alerts_mark_read_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    context.user_data["alert_cleared"] = True

    await edit_or_reply(
        update=update,
        context=context,
        text="🔔 <b>No Alerts</b>\n\nYou have no recent notifications.",
        reply_markup=back_to_menu_keyboard(),
    )
    await query.answer("Alert marked as read!")


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(alerts_menu_handler, pattern="^menu:alerts$"))
    application.add_handler(CallbackQueryHandler(alerts_mark_read_handler, pattern="^alerts:mark_read$"))
