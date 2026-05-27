"""
leaderboard.py — Rank listings of top earners, user's individual rank, and lifetime earnings.
"""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import back_to_menu_keyboard
from bot.utils import edit_or_reply, format_currency, escape_html

logger = logging.getLogger(__name__)


async def leaderboard_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the top earners rank list and user's rank info."""
    # This handler can be invoked via callback query or command /rank
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    repository = Repository(await get_db())
    
    # Get top earners
    top_list = await repository.get_top_earners(limit=10)
    user_rank = await repository.get_user_rank(user_id)
    user = await repository.get_user(user_id)

    rank_lines = []
    for rank, doc in enumerate(top_list, 1):
        name = doc.get("first_name", "User")
        uname = doc.get("username", "")
        earnings = doc.get("lifetime_earnings", 0.0)
        user_display = f"{escape_html(name)} (@{escape_html(uname)})" if uname else escape_html(name)
        
        # Highlight top 3 with special medals
        medal = "🥇" if rank == 1 else ("🥈" if rank == 2 else ("🥉" if rank == 3 else f"<b>#{rank}</b>"))
        rank_lines.append(f"{medal} {user_display} — <code>{format_currency(earnings)}</code>")

    ranks_block = "\n".join(rank_lines) if rank_lines else "<i>No ranking records available.</i>"

    # User's rank display
    user_rank_text = ""
    if user:
        user_rank_text = (
            f"👤 <b>Your Status</b>\n"
            f"• Rank: <code>#{user_rank}</code>\n"
            f"• Total Earned: <code>{format_currency(user.lifetime_earnings)}</code>"
        )

    text = (
        f"📊 <b>Global Leaderboard</b>\n\n"
        f"{ranks_block}\n\n"
        f"────────────────────\n"
        f"{user_rank_text}\n"
        f"────────────────────"
    )

    # Use the treasure image
    banner_url = await repository.get_image("img_treasure")

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=back_to_menu_keyboard(),
        image_url=banner_url
    )


async def rank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Command /rank handler."""
    await leaderboard_menu_handler(update, context)


def register_handlers(application) -> None:
    """Register leaderboard handlers."""
    application.add_handler(CallbackQueryHandler(leaderboard_menu_handler, pattern="^menu:leaderboard$"))
    application.add_handler(CommandHandler("rank", rank_command))
