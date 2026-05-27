"""
security.py — Security dashboard and admin auditing logs.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import security_menu

logger = logging.getLogger(__name__)


async def admin_security_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the security and log viewer options."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "🔒 <b>Security & Operations Logs</b>\n\n"
        "Audit administrative logs to inspect balance adjustments, warnings, bans, "
        "and settings modifications performed by all administrators."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=security_menu(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_sec_logs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View paginated admin log history."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    # Get last 50 admin logs
    logs = await repository.get_admin_logs(limit=50)
    if not logs:
        await query.answer("No administrative logs found.", show_alert=True)
        return

    per_page = 5
    total_pages = (len(logs) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_logs = logs[start_idx:end_idx]

    lines = []
    for doc in page_logs:
        date = doc["timestamp"].split("T")[0] if "T" in doc["timestamp"] else doc["timestamp"]
        admin = doc["admin_id"]
        action = doc["action"].upper()
        target = doc.get("target") or "System"
        details = doc.get("details", {})
        
        detail_desc = ""
        if action == "BALANCE_ADJUST":
            detail_desc = f" (Amount: {details.get('amount')})"
        elif action == "WARN_ADD":
            detail_desc = f" (Warning total: {details.get('new_warnings')})"

        lines.append(
            f"📅 <b>{date}</b> | Admin <code>{admin}</code>\n"
            f"└ <b>{action}</b> target <code>{target}</code>{detail_desc}"
        )

    text = (
        f"📜 <b>Admin Action Logs (Page {page+1}/{total_pages})</b>\n\n"
        + "\n\n".join(lines)
    )

    # Navigation keys
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:sec_logs:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:sec_logs:{page+1}"))

    keyboard = []
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin:security_menu")])

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


def register_handlers(application) -> None:
    """Register security handlers."""
    application.add_handler(CallbackQueryHandler(admin_security_menu_handler, pattern="^admin:security_menu$"))
    application.add_handler(CallbackQueryHandler(admin_sec_logs_handler, pattern="^admin:sec_logs:\d+$"))
