"""
auth.py — Authentication and authorization middleware.
Handles ban checks, force-subscribe channel verification, and contact sharing gates.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple
from telegram import Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from bot.database.repository import Repository
from bot.keyboards.user_kb import fsub_keyboard, contact_keyboard
from config.settings import settings

logger = logging.getLogger(__name__)


async def check_channel_membership(
    bot,
    user_id: int,
    channel_id: str,
) -> bool:
    """Check if user is a member of a specific channel."""
    try:
        # Convert channel_id to int if it's numeric/starts with -100
        chat_id: int | str = channel_id
        if str(channel_id).replace("-", "").isdigit():
            chat_id = int(channel_id)
            
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ]
    except BadRequest as e:
        if "chat not found" in str(e).lower() or "user not found" in str(e).lower():
            logger.warning("Fsub check failed for channel %s, user %d: %s", channel_id, user_id, e)
        return False
    except Exception as exc:
        logger.error("Unexpected error in membership check for channel %s: %s", channel_id, exc)
        return False


async def get_unjoined_channels(
    bot,
    user_id: int,
    repository: Repository,
) -> List[dict]:
    """Return a list of force-subscribe channels the user has NOT joined yet."""
    fsub_channels = await repository.get_fsub_channels()
    if not fsub_channels:
        return []

    unjoined = []
    for chan in fsub_channels:
        chan_id = chan.get("id")
        if chan_id:
            is_member = await check_channel_membership(bot, user_id, chan_id)
            if not is_member:
                unjoined.append(chan)
    return unjoined


async def check_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    repository: Repository,
) -> bool:
    """
    Check user authorization gates:
    1. Ban check -> strictly block
    2. Force-Subscribe check -> prompt fsub keyboard
    3. Contact share check -> prompt contact share button
    
    Returns True if user passes all checks, False otherwise.
    Automatically sends/edits message to show the relevant gate screen.
    """
    user = update.effective_user
    if not user:
        return False

    user_id = user.id
    bot = context.bot

    # Fetch user from database
    db_user = await repository.get_user(user_id)
    if not db_user:
        # Create user profile if missing (start handler handles deep-links, this is a fallback)
        username = user.username
        first_name = user.first_name
        db_user = await repository.create_user(user_id, username, first_name)

    # 1. Ban Check
    if db_user.banned:
        ban_msg = await repository.get_setting("ban_message", "🚫 <b>You have been permanently banned.</b>")
        if update.callback_query:
            await update.callback_query.answer("🚫 You are banned.", show_alert=True)
            await update.callback_query.edit_message_text(ban_msg, parse_mode="HTML")
        elif update.message:
            await update.message.reply_text(ban_msg, parse_mode="HTML")
        return False

    # 2. Force-Subscribe Check
    unjoined = await get_unjoined_channels(bot, user_id, repository)
    if unjoined:
        fsub_banner = await repository.get_image("img_channel_task")
        fsub_text = (
            "⚠️ <b>Access Denied!</b>\n\n"
            "<blockquote>To use the bot, you must join our official channels. "
            "Please join the channels listed below and click Verify.</blockquote>"
        )
        kb = fsub_keyboard(unjoined)
        
        if update.callback_query:
            # Avoid sending new photo if it was already a photo menu, but to keep UI robust:
            try:
                if fsub_banner:
                    # Send as new photo or edit message
                    await update.callback_query.answer("⚠️ Please join our channels first!")
                    # Check if current message has photo, if yes we might replace media, else send text
                    await update.callback_query.delete_message()
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=fsub_banner,
                        caption=fsub_text,
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                else:
                    await update.callback_query.edit_message_text(fsub_text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                try:
                    await update.callback_query.edit_message_text(fsub_text, reply_markup=kb, parse_mode="HTML")
                except Exception:
                    pass
        elif update.message:
            if fsub_banner:
                await update.message.reply_photo(
                    photo=fsub_banner,
                    caption=fsub_text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(fsub_text, reply_markup=kb, parse_mode="HTML")
        return False

    # 3. Contact Share Check (Phone verification)
    require_contact = await repository.get_setting("require_contact", True)
    if db_user.phone_number:
        context.user_data["contact_verified"] = True
    if require_contact and not db_user.phone_number and not context.user_data.get("contact_verified"):
        contact_text = (
            "📱 <b>Mobile Verification Required!</b>\n\n"
            "<blockquote>We require mobile verification to prevent botting and multi-accounting.\n"
            "Click the button below to share your phone number. Your phone number is never shared with third parties.</blockquote>"
        )
        kb = contact_keyboard()
        if update.callback_query:
            await update.callback_query.answer("📱 Phone verification required!")
            # Send message with reply keyboard (requires deleting the inline message first)
            await update.callback_query.delete_message()
            await bot.send_message(
                chat_id=user_id,
                text=contact_text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        elif update.message:
            await update.message.reply_text(
                text=contact_text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        return False

    return True
