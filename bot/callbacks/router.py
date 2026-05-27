"""
router.py — Central callback router and dynamic custom command dispatcher.
Interprets dynamic commands (like /help, /support) from database configurations on the fly.
"""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters

from bot.database import get_db, Repository
from bot.middlewares.auth import check_access
from bot.utils import edit_or_reply, escape_html

logger = logging.getLogger(__name__)


async def dynamic_command_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Dispatcher to process dynamic custom commands stored in MongoDB by admins.
    E.g., if a user sends `/help` or `/rules` and it matches a database record.
    """
    msg = update.message
    if not msg or not msg.text or not msg.text.startswith("/"):
        return

    # Extract command keyword (e.g. "/support" -> "support")
    text_parts = msg.text.strip().split()
    cmd_trigger = text_parts[0][1:].lower()

    repository = Repository(await get_db())
    
    # 1. Run standard access checks (e.g. bans, forced subscriptions)
    # We pass update and check_access to ensure blocked users can't run custom commands
    passed = await check_access(update, context, repository)
    if not passed:
        return

    # 2. Lookup command name in dynamic commands config
    custom_cmds = await repository.get_custom_commands()
    cmd = custom_cmds.get(cmd_trigger)
    if not cmd:
        # Ignore unmapped / commands so standard handlers/fallbacks can process them
        return

    cmd_type = cmd.get("type", "text")
    file_id = cmd.get("file_id")
    content = cmd.get("content", "")

    try:
        if cmd_type == "photo" and file_id:
            await msg.reply_photo(
                photo=file_id,
                caption=content,
                parse_mode="HTML"
            )
        else:
            await msg.reply_text(
                text=content,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    except Exception as exc:
        logger.error("Failed to dispatch custom command /%s: %s", cmd_trigger, exc)
        await msg.reply_text("⚠️ Failed to execute command. Please try again later.")


async def fallback_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback handler to answer unhandled callback queries to prevent UI spinner hangs."""
    query = update.callback_query
    if not query:
        return
    
    logger.debug("Unhandled callback query: %s", query.data)
    try:
        await query.answer()
    except Exception:
        pass


def register_router(application) -> None:
    """Register dynamic dispatcher and callback fallbacks."""
    # Register dynamic command dispatcher.
    # We place it in Group 0, but as a general MessageHandler it runs if no static CommandHandler matched.
    application.add_handler(MessageHandler(
        filters.COMMAND,
        dynamic_command_dispatcher
    ))
    
    # Low priority callback fallback handler to catch unhandled triggers
    application.add_handler(CallbackQueryHandler(
        fallback_callback_handler,
        pattern=".*"
    ), group=9)
