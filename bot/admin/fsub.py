"""
fsub.py — Admin workflows to manage force-subscribe channels.
Allows adding channels via forwarded messages or string splits.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageOriginChannel, MessageOriginChat
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import fsub_channels_keyboard
from bot.utils import escape_html

logger = logging.getLogger(__name__)


async def admin_fsub_channels_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show force-subscribe channels."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    repository = Repository(await get_db())
    await repository.update_setting("_admin_pending_fsub_action", "")
    channels = await repository.get_fsub_channels()

    text = (
        "📣 <b>Force-Subscribe Channels</b>\n\n"
        "Configure mandatory channels that users must join before unlocking bot access. "
        "Each channel will display in the welcome gate as a join link."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=fsub_channels_keyboard(channels),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_fsub_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for fsub channel details."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_fsub_channel"

    repository = Repository(await get_db())
    await repository.update_setting("_admin_pending_fsub_action", "awaiting_fsub_channel")

    text = (
        "➕ <b>Add Force-Subscribe Channel</b>\n\n"
        "👉 Please <b>FORWARD</b> a message from the target channel directly into this chat.\n"
        "The bot will automatically extract the ID and link.\n\n"
        "Alternatively, send the details manually in this format:\n"
        "<code>channel_id|channel_url|title</code>\n"
        "e.g. <code>-100987654321|https://t.me/news_channel|News Hub</code>"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:set_fsub")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_fsub_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process forwarded channels or text/URL input for fsub."""
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    repository = Repository(await get_db())

    admin_state = context.user_data.get("admin_state", "")
    if not admin_state:
        admin_state = await repository.get_setting("_admin_pending_fsub_action", "")
    if not admin_state:
        return

    if admin_state == "awaiting_fsub_channel":
        await _handle_fsub_channel_input(update, context, msg, repository)
    elif admin_state == "awaiting_fsub_channel_url":
        await _handle_fsub_url_input(update, context, msg, repository)


async def _handle_fsub_channel_input(update, context, msg, repository):
    """Handle forwarded channel message or pipe-separated text."""
    text = msg.text.strip() if msg.text else ""
    chan_id = None
    chan_url = None
    chan_title = None

    if msg.forward_origin and isinstance(msg.forward_origin, (MessageOriginChannel, MessageOriginChat)):
        chat = msg.forward_origin.chat if isinstance(msg.forward_origin, MessageOriginChannel) else msg.forward_origin.sender_chat
        if chat.type == "channel":
            chan_id = str(chat.id)
            chan_title = chat.title
            if chat.username:
                chan_url = f"https://t.me/{chat.username}"
            else:
                await msg.reply_text(
                    "⚠️ Forwarded successfully, but channel is private (no username).\n"
                    "Please send the public invite link URL for this channel so users can join."
                )
                context.user_data["fwd_fsub_id"] = chan_id
                context.user_data["fwd_fsub_title"] = chan_title
                context.user_data["admin_state"] = "awaiting_fsub_channel_url"
                await repository.update_setting("_admin_pending_fsub_action", "awaiting_fsub_channel_url")
                await repository.update_setting("_admin_pending_fsub_id", chan_id)
                await repository.update_setting("_admin_pending_fsub_title", chan_title)
                return
        else:
            await msg.reply_text("❌ Forwarded chat is not a channel.")
            return
    else:
        parts = text.split("|")
        if len(parts) == 3:
            chan_id = parts[0].strip()
            chan_url = parts[1].strip()
            chan_title = parts[2].strip()
        else:
            await msg.reply_text("❌ Invalid format. Please forward a channel message or send in correct format.")
            return

    context.user_data.pop("admin_state", None)
    await repository.update_setting("_admin_pending_fsub_action", "")
    await save_fsub_channel(update, context, repository, chan_id, chan_url, chan_title)


async def _handle_fsub_url_input(update, context, msg, repository):
    """Handle URL sent for private-channel forward."""
    url = msg.text.strip()
    if not url.startswith("https://"):
        await msg.reply_text("❌ Please send a valid channel join URL starting with https://")
        return

    chan_id = context.user_data.pop("fwd_fsub_id", "") or await repository.get_setting("_admin_pending_fsub_id", "")
    chan_title = context.user_data.pop("fwd_fsub_title", "") or await repository.get_setting("_admin_pending_fsub_title", "")
    context.user_data.pop("admin_state", None)
    await repository.update_setting("_admin_pending_fsub_action", "")

    await save_fsub_channel(update, context, repository, chan_id, url, chan_title)


async def save_fsub_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, repository: Repository, chan_id: str, chan_url: str, chan_title: str) -> None:
    """Save force subscribe channel object to settings."""
    channel_dict = {
        "id": chan_id,
        "url": chan_url,
        "title": chan_title
    }
    await repository.add_fsub_channel(channel_dict)
    
    await update.message.reply_text(
        f"✅ <b>Forced Sub Channel Linked!</b>\n\n"
        f"• <b>Title:</b> {escape_html(chan_title)}\n"
        f"• <b>ID:</b> <code>{chan_id}</code>\n"
        f"• <b>Url:</b> {chan_url}",
        parse_mode="HTML"
    )
    
    # Reload list
    channels = await repository.get_fsub_channels()
    await update.message.reply_text(
        "📣 Active force-subscribe channels list updated.",
        reply_markup=fsub_channels_keyboard(channels)
    )


async def admin_fsub_remove_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a channel from fsub array."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    chan_id = query.data.replace("admin:fsub_rem:", "")
    repository = Repository(await get_db())
    
    await repository.remove_fsub_channel(chan_id)
    await query.answer("Channel removed successfully!")

    # Reload list
    channels = await repository.get_fsub_channels()
    await query.edit_message_reply_markup(reply_markup=fsub_channels_keyboard(channels))


def register_handlers(application) -> None:
    """Register fsub handlers."""
    application.add_handler(CallbackQueryHandler(admin_fsub_channels_handler, pattern="^admin:set_fsub$"))
    application.add_handler(CallbackQueryHandler(admin_fsub_add_start, pattern="^admin:fsub_add$"))
    application.add_handler(CallbackQueryHandler(admin_fsub_remove_handler, pattern="^admin:fsub_rem:-?\d+$"))
    
    application.add_handler(MessageHandler(
        (filters.TEXT & ~filters.COMMAND) | (filters.FORWARDED & ~filters.COMMAND),
        admin_fsub_text_handler
    ), group=11)
