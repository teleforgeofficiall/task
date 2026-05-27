"""
notifications.py — Notification utility functions to send messages to users and admins.
Safe wrappers to swallow and log user block/deleted exceptions.
"""
from __future__ import annotations

import logging
from typing import Optional
from telegram import InlineKeyboardMarkup
from telegram.error import TelegramError, Forbidden, BadRequest
from config.settings import settings

logger = logging.getLogger(__name__)


async def notify_user(
    bot,
    user_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
    repository: Optional[object] = None
) -> bool:
    """
    Send a message to a user safely.
    Swallows exceptions if the user blocked the bot or deleted their account.
    Returns True if sent successfully, False otherwise.
    """
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=True
        )
        # Store notification in user's document for in-app alerts
        if repository:
            user = await repository.get_user(user_id)
            if user:
                notifs = user.notifications[:49]  # keep max 50
                notifs.insert(0, text[:200])
                await repository.update_user(user_id, {"notifications": notifs})
        return True
    except Forbidden:
        logger.info("Failed to notify user %d: Bot was blocked by the user.", user_id)
    except BadRequest as e:
        if "chat not found" in str(e).lower():
            logger.info("Failed to notify user %d: Chat not found.", user_id)
        else:
            logger.error("BadRequest error notifying user %d: %s", user_id, e)
    except TelegramError as e:
        logger.error("TelegramError notifying user %d: %s", user_id, e)
    return False


async def notify_admins(
    bot,
    text: str,
    repository: Optional[object] = None,
    parse_mode: str = "HTML",
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> int:
    """
    Notify all admin IDs in settings.
    Returns the count of admins successfully notified.
    """
    admin_list = settings.admin_id_list
    if not admin_list:
        logger.warning("No admin IDs configured to notify.")
        return 0

    success_count = 0
    for admin_id in admin_list:
        sent = await notify_user(
            bot=bot,
            user_id=admin_id,
            text=f"🔔 <b>[ADMIN ALERT]</b>\n\n{text}",
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        if sent:
            success_count += 1
    return success_count
