"""
export.py — Admin actions to export databases (users, withdrawals, proofs, logs) as CSV or JSON attachments.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import export_menu

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


async def admin_export_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show database exporter options."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "📂 <b>Database Exporter</b>\n\n"
        "Export database collections as standard formatted <b>CSV files</b> (perfect for Excel) "
        "or raw <b>JSON files</b>. Downloads are sent directly as file attachments."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=export_menu(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_export_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Perform collection export and send file document to admin chat."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    col_name = parts[2] # users / withdrawals / proofs / admin_logs
    fmt = parts[3] # csv / json

    repository = Repository(await get_db())
    await query.answer("🔄 Compiling export document...")

    # Fetch export data (limit to last 1000 records for server safety)
    data = await repository.export_collection(
        collection_name=col_name,
        fmt=fmt,
        limit=1000
    )

    if not data:
        await query.answer("❌ No records found or failed to compile.", show_alert=True)
        return

    today = datetime.now(IST).strftime("%Y%m%d")
    filename = f"export_{col_name}_{today}.{fmt}"

    # Convert string to file object
    file_bytes = io.BytesIO(data.encode("utf-8"))
    file_bytes.name = filename

    try:
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=file_bytes,
            caption=(
                f"📂 <b>Export Completed!</b>\n\n"
                f"• Collection: <code>{col_name.upper()}</code>\n"
                f"• Format: <code>{fmt.upper()}</code>\n"
                f"• Records exported: <code>Up to 1000</code>"
            ),
            parse_mode="HTML"
        )
    except Exception as exc:
        logger.exception("Failed to send export document: %s", exc)
        await query.answer("❌ Failed to send document.", show_alert=True)


def register_handlers(application) -> None:
    """Register exporter handlers."""
    application.add_handler(CallbackQueryHandler(admin_export_menu_handler, pattern="^admin:export_menu$"))
    application.add_handler(CallbackQueryHandler(admin_export_action_handler, pattern="^admin:exp:(users|withdrawals|proofs|admin_logs):(csv|json)$"))
