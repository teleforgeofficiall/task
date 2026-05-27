"""
dashboard.py — Real-time bot analytics dashboard.
"""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import back_to_admin
from bot.utils import format_currency

logger = logging.getLogger(__name__)


async def admin_dashboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render live bot stats and database aggregates."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    stats = await repository.get_dashboard_stats()

    text = (
        f"📊 <b>TASKHUB Live Analytics</b>\n"
        f"─────────────────────\n"
        f"👥 <b>User Base:</b>\n"
        f"• Total registered: <code>{stats['total_users']}</code>\n"
        f"• Active (7d): <code>{stats['active_users']}</code>\n"
        f"• Joined today: <code>{stats['today_joined']}</code>\n\n"
        f"🔒 <b>Security & Health:</b>\n"
        f"• Flagged (Fraud Score > 50): <code>{stats['suspicious']}</code>\n"
        f"• Banned accounts: <code>{stats['banned']}</code>\n\n"
        f"⏳ <b>Pending Actions Queue:</b>\n"
        f"• Task proofs reviewing: <code>{stats['pending_proofs']}</code>\n"
        f"• Pending withdrawals: <code>{stats['pending_withdrawals']}</code>\n\n"
        f"💰 <b>Financial Statistics:</b>\n"
        f"• Total payouts approved: <b>{format_currency(stats['total_paid'])}</b>\n"
        f"• Total user earnings: <b>{format_currency(stats['total_earnings'])}</b>\n"
        f"─────────────────────"
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=back_to_admin(),
            parse_mode="HTML"
        )
        await query.answer()
    except Exception as exc:
        logger.exception("Failed to render dashboard: %s", exc)


def register_handlers(application) -> None:
    """Register dashboard handlers."""
    application.add_handler(CallbackQueryHandler(admin_dashboard_handler, pattern="^admin:dashboard$"))
