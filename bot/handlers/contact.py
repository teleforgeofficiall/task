"""
contact.py — Handler for contact verification (phone sharing) to prevent botting/multi-accounting.
"""
from __future__ import annotations

import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, MessageHandler, filters

from bot.database import get_db, Repository
from bot.security.fraud_detector import calculate_fraud_score
from bot.services.notifications import notify_user, notify_admins
from bot.handlers.start import send_main_menu
from config.settings import settings

logger = logging.getLogger(__name__)


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle contact sharing.
    Saves the user's phone number, triggers fraud detection scoring,
    and forwards the user to the main menu.
    """
    msg = update.message
    if not msg or not msg.contact:
        return

    contact = msg.contact
    user_id = msg.from_user.id

    # Security check: Ensure the contact user_id matches the message sender's user_id
    if contact.user_id != user_id:
        await msg.reply_text(
            "❌ <b>Security Gate Failed!</b>\n\n"
            "You must share your own contact info by tapping the button.\n"
            "Please try again.",
            parse_mode="HTML"
        )
        return

    repository = Repository(await get_db())
    
    # Save phone number
    await repository.update_user_fields(
        user_id=user_id,
        phone_number=contact.phone_number
    )

    # Flag in user_data so middleware doesn't re-prompt (DB backup in case of reload)
    context.user_data["contact_verified"] = True

    # Delete the earlier contact-prompt message if we stored its message_id
    prompt_msg_id = context.user_data.pop("contact_prompt_msg_id", None)
    if prompt_msg_id:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=prompt_msg_id)
        except Exception:
            pass

    # Delete user's contact message
    try:
        await msg.delete()
    except Exception:
        pass

    # Fetch updated user profile and calculate fraud heuristics
    user = await repository.get_user(user_id)
    if user:
        await calculate_fraud_score(repository, user)

    # Forward phone number to all admins
    for admin_id in settings.admin_id_list:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📱 <b>New Phone Verification</b>\n\n"
                    f"👤 <b>User:</b> {msg.from_user.first_name}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                    f"📞 <b>Phone:</b> <code>{contact.phone_number}</code>\n"
                    f"👤 <b>Username:</b> @{msg.from_user.username or 'N/A'}"
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ <b>Phone number verified successfully!</b>",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception:
        pass

    await send_main_menu(update, context, repository)


def register_handlers(application) -> None:
    """Register contact sharing handlers."""
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))
