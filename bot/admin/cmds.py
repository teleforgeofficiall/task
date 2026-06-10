"""
cmds.py — Admin interface to define custom reply commands.
Allows dynamically linking triggers (like /support, /help) to customized bot outputs.
"""
from __future__ import annotations

import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import custom_cmds_keyboard
from bot.utils import escape_html

logger = logging.getLogger(__name__)


async def admin_custom_cmds_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show custom commands list."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    repository = Repository(await get_db())
    cmds = await repository.get_custom_commands()

    text = (
        "📟 <b>Custom Command Manager</b>\n\n"
        "Create static reply triggers (e.g. <code>/support</code>, <code>/rules</code>) "
        "returning custom text or photo banners instantly to users."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=custom_cmds_keyboard(cmds),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_cmd_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for command name."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_cmd_name"

    text = (
        "➕ <b>Add Custom Command</b>\n\n"
        "Please send the name of the command trigger (e.g. <code>help</code> for <code>/help</code> or <code>rules</code>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:set_custom_cmds")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_cmds_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming command names and contents."""
    if context.user_data is None:
        return
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("awaiting_cmd_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip() if msg.text else ""
    repository = Repository(await get_db())

    # Step 1: Receiving name
    if admin_state == "awaiting_cmd_name":
        if not text:
            await msg.reply_text("❌ Command name cannot be empty.")
            return

        # Sanitize command name (alphanumeric and underscores only, strip leading slash)
        name = re.sub(r"[^a-zA-Z0-9_]", "", text.lstrip("/")).lower()
        if not name:
            await msg.reply_text("❌ Invalid command name. Use alphanumeric characters only.")
            return

        context.user_data["new_cmd_name"] = name
        context.user_data["admin_state"] = "awaiting_cmd_content"

        await msg.reply_text(
            f"➕ <b>Create /{name} — Step 2</b>\n\n"
            f"Please send the message that the command will reply with.\n\n"
            f"• You can send <b>formatted text</b>.\n"
            f"• Or send a <b>photo with a caption</b>.\n\n"
            f"<i>Type /cancel to abort.</i>",
            parse_mode="HTML"
        )
        return

    # Step 2: Receiving message
    if admin_state == "awaiting_cmd_content":
        name = context.user_data.pop("new_cmd_name")
        context.user_data.pop("admin_state", None)

        if text.lower() == "/cancel":
            await msg.reply_text("❌ Trigger creation aborted.", reply_markup=back_to_admin())
            return

        cmd_data = {}
        if msg.photo:
            cmd_data = {
                "type": "photo",
                "file_id": msg.photo[-1].file_id,
                "content": msg.caption or ""
            }
        else:
            cmd_data = {
                "type": "text",
                "file_id": None,
                "content": text
            }

        # Save to DB
        await repository.set_custom_command(name, cmd_data)
        
        await msg.reply_text(
            f"✅ Custom command <b>/{name}</b> successfully created!",
            parse_mode="HTML"
        )

        # Reload list
        cmds = await repository.get_custom_commands()
        await msg.reply_text(
            "📟 Active custom commands list updated.",
            reply_markup=custom_cmds_keyboard(cmds)
        )


async def admin_cmd_remove_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a custom command."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    cmd_name = query.data.replace("admin:cmd_del:", "")
    repository = Repository(await get_db())

    await repository.delete_custom_command(cmd_name)
    await query.answer(f"Deleted /{cmd_name} successfully!")

    # Reload list
    cmds = await repository.get_custom_commands()
    await query.edit_message_reply_markup(reply_markup=custom_cmds_keyboard(cmds))


def register_handlers(application) -> None:
    """Register custom commands admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_custom_cmds_handler, pattern="^admin:set_custom_cmds$"))
    application.add_handler(CallbackQueryHandler(admin_cmd_add_start, pattern="^admin:cmd_add$"))
    application.add_handler(CallbackQueryHandler(admin_cmd_remove_handler, pattern="^admin:cmd_del:[a-z0-9_]+$"))
    
    # Text input and media handlers
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        admin_cmds_text_handler
    ), group=20)
