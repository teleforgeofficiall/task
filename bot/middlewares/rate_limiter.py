"""
rate_limiter.py — Anti-flood, anti-spam, and callback debounce middleware.
Implements rate limiting using a custom PTB pre-handler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop, TypeHandler
from config.settings import settings

logger = logging.getLogger(__name__)

# In-memory stores for rate limiting
# user_id -> list of float timestamps
_message_timestamps = defaultdict(list)
# user_id -> datetime when mute expires
_muted_users = {}
# user_id -> float timestamp of last callback query click
_last_callback_times = {}


async def rate_limiter_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Middleware running in Group -1.
    Prevents flood spam (messages) and double clicks (callback queries).
    """
    user = update.effective_user
    if not user:
        return

    user_id = user.id
    now = datetime.now(timezone.utc).timestamp()

    # 1. Check if user is muted
    mute_expiry = _muted_users.get(user_id)
    if mute_expiry:
        if now < mute_expiry:
            # User is still muted
            if update.callback_query:
                await update.callback_query.answer(
                    "🚫 You are muted due to spamming. Please wait.",
                    show_alert=True
                )
            elif update.message:
                remaining = int(mute_expiry - now)
                await update.message.reply_text(
                    f"🚫 <b>You are temporarily muted for spamming.</b>\n"
                    f"Please wait {remaining}s before trying again.",
                    parse_mode="HTML"
                )
            raise ApplicationHandlerStop()
        else:
            # Mute expired, clean up
            _muted_users.pop(user_id, None)

    # 2. Handle Callback Query Debounce (double-click prevention)
    if update.callback_query:
        last_click = _last_callback_times.get(user_id, 0.0)
        if now - last_click < 1.0:
            # Debounce block
            logger.debug("Debouncing callback query click for user %d", user_id)
            await update.callback_query.answer("⏳ Please wait...")
            raise ApplicationHandlerStop()
        _last_callback_times[user_id] = now

    # 3. Handle Message Rate Limiter (Anti-Flood)
    if update.message:
        user_history = _message_timestamps[user_id]
        
        # Clean older timestamps
        user_history = [t for t in user_history if now - t < 10.0]
        user_history.append(now)
        _message_timestamps[user_id] = user_history

        # Check last 3 seconds (strict settings.RATE_LIMIT_WINDOW)
        recent_3s = [t for t in user_history if now - t < settings.RATE_LIMIT_WINDOW]
        if len(recent_3s) > settings.RATE_LIMIT_MESSAGES:
            # Rate limit exceeded
            # Check for high volume spam (e.g. 10 messages within 10 seconds)
            if len(user_history) >= 10:
                mute_duration = settings.FLOOD_MUTE_SECONDS
                _muted_users[user_id] = now + mute_duration
                logger.warning("User %d muted for %d seconds due to spamming.", user_id, mute_duration)
                await update.message.reply_text(
                    f"⚠️ <b>Spam detected!</b>\n"
                    f"You have been muted for {mute_duration} seconds.",
                    parse_mode="HTML"
                )
            else:
                # Warning warning
                await update.message.reply_text(
                    "⚠️ <b>Please slow down!</b>\n"
                    "Do not flood the bot with rapid commands.",
                    parse_mode="HTML"
                )
            raise ApplicationHandlerStop()


def setup_rate_limiter(application) -> None:
    """Register rate limiter middleware in Group -1 (runs before other handlers)."""
    # Group -1 ensures this handler executes first
    application.add_handler(TypeHandler(Update, rate_limiter_middleware), group=-1)
