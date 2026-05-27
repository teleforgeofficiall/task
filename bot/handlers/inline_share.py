from __future__ import annotations

import logging

from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, InlineQueryHandler

from bot.database import get_db, Repository

logger = logging.getLogger(__name__)


async def inline_share_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for sharing referral links with buttons."""
    query = update.inline_query
    if not query or not query.query:
        return

    text = query.query.strip()
    if not text.startswith("ref_"):
        return

    try:
        user_id = int(text.split("_")[1])
    except (ValueError, IndexError):
        return

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    msg_text = (
        f"🚀 <b>Earn Real Money with TaskHub!</b>\n\n"
        f"<blockquote>Complete simple tasks, invite friends, "
        f"and get <b>instant payouts</b> directly to your wallet.</blockquote>\n\n"
        f"<b>What you get:</b>\n"
        f"• 💰 <b>Paid tasks</b> — earn ₹ per task\n"
        f"• 🤝 <b>Referral rewards</b> — earn when friends join\n"
        f"• 💳 <b>Instant withdrawals</b> — no waiting\n\n"
        f"👇 <b>Tap below to start earning:</b>"
    )

    results = [
        InlineQueryResultArticle(
            id="1",
            title="📤 Share Referral Link",
            description="Send this to your friends so they can join TaskHub!",
            input_message_content=InputTextMessageContent(
                message_text=msg_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Start Earning", url=ref_link)]
            ])
        )
    ]

    await query.answer(results, cache_time=1, is_personal=True)


def register_handlers(application) -> None:
    """Register inline query handler."""
    application.add_handler(InlineQueryHandler(inline_share_handler, pattern=r"^ref_\d+$"))
