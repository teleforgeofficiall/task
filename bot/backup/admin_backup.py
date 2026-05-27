"""
admin_backup.py — Telegram admin handlers for Backup & Restore management.
Adds backup UI to the admin inline keyboard panel.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.admin.panel import is_admin
from bot.backup.manager import BackupManager, BackupError
from bot.database import get_db, Repository
from bot.utils import escape_html
from config.settings import settings

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

_backup_manager = BackupManager()


def _format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


async def backup_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main backup & restore menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    # Get stats
    backups = await _backup_manager.list_backups()
    total_size = await _backup_manager.get_backup_size_total()

    text = (
        "💾 <b>Backup & Restore Manager</b>\n\n"
        f"📁 Backup Directory: <code>{escape_html(_backup_manager.backup_dir.as_posix())}</code>\n"
        f"📦 Total Backups: <b>{len(backups)}</b>\n"
        f"💿 Total Size: <b>{_format_size(total_size)}</b>\n"
        f"🔄 Auto-Cleanup: <b>{settings.BACKUP_RETENTION_DAYS} days</b>\n\n"
        "Use the buttons below to manage your PostgreSQL backups."
    )

    keyboard = [
        [InlineKeyboardButton("➕ Create Backup Now", callback_data="admin:backup_create")],
        [InlineKeyboardButton("📋 View Backup History", callback_data="admin:backup_list:0")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    await query.answer()


async def backup_create_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new backup."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    await query.edit_message_text(
        text="⏳ <b>Creating backup...</b>\n\nPlease wait, this may take a moment.",
        parse_mode="HTML",
    )
    await query.answer()

    try:
        result = await _backup_manager.create_backup()
        size_str = _format_size(result["file_size_bytes"])

        text = (
            "✅ <b>Backup Created Successfully!</b>\n\n"
            f"📄 File: <code>{escape_html(result['filename'])}</code>\n"
            f"💿 Size: <b>{size_str}</b>\n"
            f"🕐 Time: {result['created_at']}\n\n"
        )

        keyboard = [
            [InlineKeyboardButton("📥 Download Backup", callback_data=f"admin:backup_download:{result['filename']}")],
            [InlineKeyboardButton("📋 View All Backups", callback_data="admin:backup_list:0")],
            [InlineKeyboardButton("🔙 Back to Backup Menu", callback_data="admin:backup_menu")],
        ]

        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )

    except BackupError as exc:
        text = f"❌ <b>Backup Failed</b>\n\n<code>{escape_html(str(exc))}</code>"
        await context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Try Again", callback_data="admin:backup_menu")],
            ]),
            parse_mode="HTML",
        )


async def backup_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List backup history with pagination."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    data = query.data.split(":")
    page = int(data[-1]) if len(data) > 2 else 0
    per_page = 5

    backups = await _backup_manager.list_backups()
    # Also get records from DB
    repository = Repository(await get_db())
    db_records = await repository.get_backup_records(limit=50)

    total_pages = max(1, (len(backups) + per_page - 1) // per_page)
    page = min(page, total_pages - 1)
    start = page * per_page
    end = start + per_page
    page_backups = backups[start:end]

    text = "📋 <b>Backup History</b>\n\n"
    if not backups:
        text += "No backups found. Create your first backup!"
    else:
        text += f"Total backups: <b>{len(backups)}</b>\n\n"
        for i, b in enumerate(page_backups, start + 1):
            size_str = _format_size(b.get("file_size_bytes", 0))
            created = b.get("created_at", "unknown")[:19]
            text += f"{i}. <code>{escape_html(b['filename'])}</code>\n"
            text += f"   📦 {size_str} | 🕐 {created}\n\n"

    keyboard = []
    for b in page_backups:
        keyboard.append([
            InlineKeyboardButton("📥 Download", callback_data=f"admin:backup_download:{b['filename']}"),
            InlineKeyboardButton("🗑️ Delete", callback_data=f"admin:backup_delete:{b['filename']}"),
        ])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:backup_list:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:backup_list:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("➕ Create Backup", callback_data="admin:backup_create")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Backup Menu", callback_data="admin:backup_menu")])

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    await query.answer()


async def backup_download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a backup file to the admin."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    data = query.data.split(":")
    filename = ":".join(data[2:])  # Support filenames with colons

    filepath = _backup_manager.backup_dir / filename
    if not filepath.exists():
        await query.answer("❌ Backup file not found on disk.", show_alert=True)
        return

    await query.answer("📥 Sending backup file...")

    try:
        with open(filepath, "rb") as f:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=filename,
                caption=f"📥 <b>Backup Download</b>\n\nFile: <code>{escape_html(filename)}</code>",
                parse_mode="HTML",
            )
    except Exception as exc:
        await query.message.reply_text(
            f"❌ Failed to send backup: {escape_html(str(exc))}",
            parse_mode="HTML",
        )


async def backup_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a backup file and its DB record."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    data = query.data.split(":")
    filename = ":".join(data[2:])

    # Delete from disk
    deleted = await _backup_manager.delete_backup(filename)

    if deleted:
        await query.answer(f"✅ Deleted: {filename}", show_alert=True)
    else:
        await query.answer("❌ Backup file not found.", show_alert=True)

    # Refresh the list
    await backup_list_handler(update, context)


async def backup_create_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uploaded backup file for restore."""
    admin_state = context.user_data.get("admin_state", "")
    if admin_state != "awaiting_restore_file":
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    if not msg or not msg.document:
        await msg.reply_text("❌ Please send a .sql.gz backup file.")
        return

    doc = msg.document
    if not doc.file_name or not doc.file_name.endswith(".sql.gz"):
        await msg.reply_text("❌ Invalid file format. Please send a .sql.gz backup file.")
        return

    await msg.reply_text("⏳ <b>Downloading backup file...</b>", parse_mode="HTML")

    try:
        # Download the file
        tg_file = await doc.get_file()
        filepath = _backup_manager.backup_dir / doc.file_name
        await tg_file.download_to_drive(filepath)

        await msg.reply_text(
            f"✅ File downloaded: <code>{escape_html(doc.file_name)}</code>\n\n"
            "⚠️ <b>WARNING:</b> Restoring will <b>DELETE ALL CURRENT DATA</b> and replace it with the backup.\n\n"
            "Are you sure you want to proceed?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes, Restore", callback_data=f"admin:backup_restore_confirm:{doc.file_name}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="admin:backup_menu")],
            ]),
            parse_mode="HTML",
        )
    except Exception as exc:
        await msg.reply_text(f"❌ Download failed: {escape_html(str(exc))}", parse_mode="HTML")

    context.user_data.pop("admin_state", None)


async def backup_restore_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm and execute restore."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    data = query.data.split(":")
    filename = ":".join(data[2:])
    filepath = _backup_manager.backup_dir / filename

    if not filepath.exists():
        await query.answer("❌ Backup file not found.", show_alert=True)
        return

    await query.edit_message_text(
        text=f"⏳ <b>Restoring database from:</b>\n<code>{escape_html(filename)}</code>\n\nPlease wait...",
        parse_mode="HTML",
    )
    await query.answer()

    try:
        result = await _backup_manager.restore_backup(str(filepath))

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"✅ <b>Database Restored Successfully!</b>\n\n{escape_html(result['message'])}\n\n"
                 "⚠️ Bot will restart automatically.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Backup Menu", callback_data="admin:backup_menu")],
            ]),
            parse_mode="HTML",
        )
    except BackupError as exc:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"❌ <b>Restore Failed</b>\n\n<code>{escape_html(str(exc))}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Backup Menu", callback_data="admin:backup_menu")],
            ]),
            parse_mode="HTML",
        )


def register_handlers(application) -> None:
    """Register backup admin handlers."""
    application.add_handler(CallbackQueryHandler(backup_menu_handler, pattern="^admin:backup_menu$"))
    application.add_handler(CallbackQueryHandler(backup_create_handler, pattern="^admin:backup_create$"))
    application.add_handler(CallbackQueryHandler(backup_list_handler, pattern=r"^admin:backup_list:\d+$"))
    application.add_handler(CallbackQueryHandler(backup_download_handler, pattern=r"^admin:backup_download:"))
    application.add_handler(CallbackQueryHandler(backup_delete_handler, pattern=r"^admin:backup_delete:"))
    application.add_handler(CallbackQueryHandler(backup_restore_confirm_handler, pattern=r"^admin:backup_restore_confirm:"))
    # File upload handler for restore
    application.add_handler(
        MessageHandler(filters.Document.FileExtension("gz"), backup_create_file_handler),
        group=6,
    )
