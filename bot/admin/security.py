"""
security.py — Security dashboard: Contact Mandatory, Device Verification, URL config.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from config.settings import settings

logger = logging.getLogger(__name__)


async def admin_security_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show security dashboard with Contact/Device toggles."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())

    contact = await repository.get_setting("require_contact", True)
    device = await repository.get_setting("device_verification_enabled", False)
    verif_url = await repository.get_setting("device_verification_url", "")

    text = (
        "🔒 <b>Security Dashboard</b>\n\n"
        f"📞 <b>Contact Mandatory:</b> {'ON ✅' if contact else 'OFF ❌'}\n"
        f"🔐 <b>Device Verification:</b> {'ON ✅' if device else 'OFF ❌'}\n"
        + (f"🌐 <b>Verify URL:</b> <code>{verif_url}</code>\n" if verif_url else "")
        + "\nToggle options below. Only one verification method can be active at a time."
    )

    from bot.keyboards.admin_kb import security_menu
    await query.edit_message_text(text=text, reply_markup=security_menu(contact, device), parse_mode="HTML")
    await query.answer()


async def admin_sec_toggle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle Contact Mandatory ON/OFF. Disables Device Verification when ON."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("require_contact", True)
    new_val = not current
    await repository.update_setting("require_contact", new_val)
    if new_val:
        await repository.update_setting("device_verification_enabled", False)
    await query.answer(f"Contact Mandatory {'ON ✅' if new_val else 'OFF ❌'}!")
    await admin_security_menu_handler(update, context)


async def admin_sec_toggle_device(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle Device Verification ON/OFF. Disables Contact when ON."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("device_verification_enabled", False)
    new_val = not current
    await repository.update_setting("device_verification_enabled", new_val)
    if new_val:
        await repository.update_setting("require_contact", False)
    await query.answer(f"Device Verification {'ON ✅' if new_val else 'OFF ❌'}!")
    await admin_security_menu_handler(update, context)


async def admin_sec_set_url_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin to set device verification URL."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "sec_set_verif_url"
    repository = Repository(await get_db())
    current = await repository.get_setting("device_verification_url", "")

    text = (
        "🔧 <b>Set Device Verification URL</b>\n\n"
        "Send the Render deployment URL for the verification page.\n"
        "Example: <code>https://teleforge-task-earn.onrender.com</code>\n\n"
        f"Current: {f'<code>{current}</code>' if current else '<i>Not set</i>'}\n\n"
        "Tap ❌ Cancel to abort."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:security_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_sec_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process text input for security settings."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("sec_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()
    repository = Repository(await get_db())

    if admin_state == "sec_set_verif_url":
        url = text.rstrip("/")
        if not settings.is_production:
            url = url.replace("localhost", "127.0.0.1")
        await repository.update_setting("device_verification_url", url)
        await msg.reply_text(f"✅ Verification URL set to:\n<code>{url}</code>", parse_mode="HTML")

    context.user_data.pop("admin_state", None)
    # Re-fetch and show the security menu as a new message
    contact = await repository.get_setting("require_contact", True)
    device = await repository.get_setting("device_verification_enabled", False)
    new_verif_url = await repository.get_setting("device_verification_url", "")
    text = (
        "🔒 <b>Security Dashboard</b>\n\n"
        f"📞 <b>Contact Mandatory:</b> {'ON ✅' if contact else 'OFF ❌'}\n"
        f"🔐 <b>Device Verification:</b> {'ON ✅' if device else 'OFF ❌'}\n"
        + (f"🌐 <b>Verify URL:</b> <code>{new_verif_url}</code>\n" if new_verif_url else "")
        + "\nToggle options below. Only one verification method can be active at a time."
    )
    from bot.keyboards.admin_kb import security_menu
    await msg.reply_text(text=text, reply_markup=security_menu(contact, device), parse_mode="HTML")


def register_handlers(application) -> None:
    """Register security handlers."""
    application.add_handler(CallbackQueryHandler(admin_security_menu_handler, pattern="^admin:security_menu$"))
    application.add_handler(CallbackQueryHandler(admin_sec_toggle_contact, pattern="^admin:sec_toggle_contact$"))
    application.add_handler(CallbackQueryHandler(admin_sec_toggle_device, pattern="^admin:sec_toggle_device$"))
    application.add_handler(CallbackQueryHandler(admin_sec_set_url_start, pattern="^admin:sec_set_verif_url$"))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_sec_text_handler
    ), group=8)
