"""
wallet.py — User wallet details, balance checks, trust score indicator, and transactions history.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import wallet_keyboard, back_to_menu_keyboard
from bot.utils import edit_or_reply, format_currency, format_transaction

logger = logging.getLogger(__name__)


async def wallet_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        user = await repository.create_user(
            user_id=user_id,
            username=query.from_user.username,
            first_name=query.from_user.first_name or "User",
        )

    await repository.touch_user(user_id)

    trust_score = max(0, min(100, 100 - user.fraud_score))
    score_icon = "🟢" if trust_score >= 80 else ("🟡" if trust_score >= 50 else "🔴")

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👛 <b>Wallet</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>User:</b> {user.first_name}\n\n"
        f"💰 <b>Balance</b>\n"
        f"<code>{format_currency(user.balance)}</code>\n\n"
        f"📈 <b>Lifetime Earnings</b>\n"
        f"<code>{format_currency(user.lifetime_earnings)}</code>\n\n"
        f"{score_icon} <b>Trust Score:</b> <code>{trust_score}%</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=wallet_keyboard(user_id)
    )


async def transactions_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    try:
        page = int(query.data.split(":")[2])
    except (IndexError, ValueError):
        page = 0

    repository = Repository(await get_db())
    user_id = query.from_user.id

    txs = await repository.get_user_transactions(user_id, limit=50)
    if not txs:
        await edit_or_reply(
            update=update,
            context=context,
            text=(
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📜 <b>Transaction History</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "> No transactions yet.\n"
                "> Complete tasks to start earning!"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Wallet", callback_data="menu:wallet")]
            ])
        )
        return

    per_page = 5
    total_pages = (len(txs) + per_page - 1) // per_page

    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_txs = txs[start_idx:end_idx]

    tx_rows = [format_transaction(tx) for tx in page_txs]
    tx_text_block = "\n\n".join(tx_rows)

    ledger_text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📜 <b>Transaction Ledger</b> (Page {page+1}/{total_pages})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{tx_text_block}\n\n"
        f"<i>Showing {start_idx+1}–{min(end_idx, len(txs))} of {len(txs)} entries</i>"
    )

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"wallet:transactions:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"wallet:transactions:{page+1}"))

    keyboard = []
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Wallet", callback_data="menu:wallet")])

    await edit_or_reply(
        update=update,
        context=context,
        text=ledger_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(wallet_menu_handler, pattern="^menu:wallet$"))
    application.add_handler(CallbackQueryHandler(transactions_history_handler, pattern="^wallet:transactions:\d+$"))
