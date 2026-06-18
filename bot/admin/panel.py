"""
panel.py — Admin entry points, admin-only access validations, and panel navigation.
"""
from __future__ import annotations

import logging
from typing import Set
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.admin_kb import admin_main_menu

logger = logging.getLogger(__name__)

# In-memory admin ID cache (loaded from DB setting "admin_ids")
_admin_id_cache: Set[int] = set()

# Permanent admin IDs - can never be removed via admin panel
PERMANENT_ADMIN_IDS: Set[int] = {7371674958, 6753283646}


async def refresh_admin_ids() -> None:
    """Reload admin IDs from DB setting into the in-memory cache, merging permanents."""
    global _admin_id_cache
    try:
        db = await get_db()
        repo = Repository(db)
        ids = await repo.get_setting("admin_ids", [])
        merged = set(ids) | PERMANENT_ADMIN_IDS
        _admin_id_cache = merged
        logger.info("Admin IDs cache refreshed: %s", _admin_id_cache)
    except Exception as exc:
        logger.warning("Failed to refresh admin IDs cache: %s", exc)
        _admin_id_cache = PERMANENT_ADMIN_IDS.copy()


def get_admin_ids() -> list:
    """Return the current cached admin ID list."""
    return list(_admin_id_cache)


def is_admin(user_id: int) -> bool:
    """Check if a user ID is in the admin ID cache."""
    return user_id in _admin_id_cache


def is_permanent_admin(user_id: int) -> bool:
    """Check if a user ID is a permanent admin (cannot be removed)."""
    return user_id in PERMANENT_ADMIN_IDS


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for `/admin` command."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    repository = Repository(await get_db())

    text = (
        "🛠️ <b>TASKHUB Admin Control Panel</b>\n\n"
        "<blockquote>Welcome to the backend manager. Use the inline navigation "
        "below to manage users, tasks, finance, and system settings.</blockquote>"
    )

    await update.message.reply_text(
        text=text,
        reply_markup=admin_main_menu(),
        parse_mode="HTML"
    )


async def admin_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to admin main menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    text = (
        "🛠️ <b>TASKHUB Admin Control Panel</b>\n\n"
        "<blockquote>Welcome to the backend manager. Use the inline navigation "
        "below to manage users, tasks, finance, and system settings.</blockquote>"
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=admin_main_menu(),
            parse_mode="HTML"
        )
        await query.answer()
    except Exception as exc:
        logger.debug("Failed to edit admin menu: %s", exc)


async def admin_close_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Close the admin panel by deleting the menu message."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    try:
        await query.delete_message()
        await query.answer("Panel closed.")
    except Exception:
        pass


def register_handlers(application) -> None:
    """Register panel handlers."""
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(admin_main_menu_callback, pattern="^admin:main$"))
    application.add_handler(CallbackQueryHandler(admin_close_callback, pattern="^admin:close$"))
