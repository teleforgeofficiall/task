"""
redeem_code.py — Admin Google Redeem Code inventory manager.
Generate, view, and manage redeem codes with stock tracking.
"""
from __future__ import annotations

import logging
import random
import string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.services.notifications import notify_admins
from bot.utils import format_currency, escape_html

logger = logging.getLogger(__name__)


REDEEM_AMOUNTS = [10, 25, 50, 100, 250, 500]


async def admin_redeem_manager_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main Redeem Code Manager menu with clickable inventory buttons."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())
    inventory = await repository.get_redeem_code_inventory()
    threshold = await repository.get_setting("redeem_low_stock_threshold", 5)
    enabled = await repository.get_setting("redeem_stock_enabled", True)

    keyboard = []
    for item in inventory:
        a = item["available"]
        if a == 0:
            icon = "❌"
        elif a <= threshold:
            icon = "⚠️"
        else:
            icon = "✅"
        amt = int(item["amount"])
        label = f"💰 ₹{amt} — {a} codes {icon}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"admin:rc_view_amt:{amt}:0")])

    from bot.keyboards.admin_kb import redeem_code_manager_keyboard
    action_kb = redeem_code_manager_keyboard().inline_keyboard
    keyboard.extend(action_kb)

    text = (
        "🎫 <b>Google Redeem Code Manager</b>\n\n"
        f"⚙️ Low stock alert: <code>{threshold}</code>\n"
        f"🟢 Status: <code>{'Enabled ✅' if enabled else 'Disabled ❌'}</code>\n\n"
        "Tap any amount to view its active codes:"
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def admin_redeem_add_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show amount selection for adding codes."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    keyboard = []
    row = []
    for i, amt in enumerate(REDEEM_AMOUNTS):
        row.append(InlineKeyboardButton(f"₹{amt}", callback_data=f"admin:rc_add_amt:{amt}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin:redeem_manager")])

    await query.edit_message_text(
        text="🎫 <b>Add Google Redeem Codes</b>\n\nSelect the code amount:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    await query.answer()


async def admin_redeem_add_amt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin to paste redeem codes for selected amount."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    amount = float(parts[2])
    context.user_data["admin_state"] = f"rc_add_{amount}"

    await query.edit_message_text(
        text=(
            f"🎫 <b>Add ₹{amount:.0f} Google Redeem Codes</b>\n\n"
            "Send the redeem codes below.\n"
            "You can send <b>one per line</b> or <b>comma-separated</b>.\n\n"
            "Example:\n"
            "<code>ABCD-1234-WXYZ\n"
            "EFGH-5678-IJKL\n"
            "MNOP-9012-QRST</code>\n\n"
            "Send /cancel to abort."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:redeem_manager")]
        ]),
        parse_mode="HTML",
    )
    await query.answer()


async def admin_redeem_add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process bulk redeem code text input."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("rc_add_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    amount = float(admin_state.split("_")[2])
    context.user_data.pop("admin_state", None)
    text = update.message.text.strip()

    if text.lower() == "/cancel":
        await update.message.reply_text("❌ Canceled.")
        return

    # Parse codes: split by newline or comma
    codes = []
    for line in text.split("\n"):
        for part in line.split(","):
            part = part.strip()
            if part:
                codes.append(part)

    repository = Repository(await get_db())
    added = await repository.add_redeem_codes(codes, amount)

    # Check low stock alert
    low_stock = await repository.check_redeem_low_stock()
    admin_alerts = []
    for ls in low_stock:
        admin_alerts.append(f"⚠️ ₹{ls['amount']:.0f}: only {ls['available']} codes left (threshold: {ls['threshold']})")

    await update.message.reply_text(
        f"✅ <b>{added} codes of ₹{amount:.0f} added successfully!</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 View Inventory", callback_data="admin:redeem_manager"),
             InlineKeyboardButton("➕ Add More", callback_data="admin:rc_add_code")],
        ]),
        parse_mode="HTML",
    )

    if admin_alerts:
        alert_text = "⚠️ <b>Low Stock Alert — Google Redeem Codes</b>\n\n" + "\n".join(admin_alerts)
        await notify_admins(bot=context.bot, text=alert_text)


async def admin_redeem_view_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View unused codes for a specific amount (paginated)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    amount = float(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0

    repository = Repository(await get_db())
    data = await repository.get_redeem_codes_by_amount(amount, page=page, per_page=15)

    codes = data["codes"]
    total = data["total"]
    total_pages = data["total_pages"]
    page = data["page"]

    if not codes:
        lines = "<blockquote>No unused codes for this amount.</blockquote>"
    else:
        code_list = "\n".join(f"<code>{escape_html(c)}</code>" for c in codes)
        lines = f"<blockquote>{code_list}</blockquote>"

    text = (
        f"🎫 <b>₹{amount:.0f} — Active Codes</b>\n"
        f"Total: <code>{total}</code> unused | Page {page+1}/{total_pages}\n\n"
        f"{lines}"
    )

    keyboard = []
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:rc_view_amt:{amount:.0f}:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:rc_view_amt:{amount:.0f}:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Manager", callback_data="admin:redeem_manager")])

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def admin_redeem_settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show redeem code settings."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())
    threshold = await repository.get_setting("redeem_low_stock_threshold", 5)
    enabled = await repository.get_setting("redeem_stock_enabled", True)

    text = (
        "⚙️ <b>Redeem Code Settings</b>\n\n"
        f"• <b>Low Stock Threshold:</b> <code>{threshold}</code>\n"
        f"• <b>Stock Status:</b> <code>{'Enabled ✅' if enabled else 'Disabled ❌'}</code>"
    )

    from bot.keyboards.admin_kb import redeem_code_settings_keyboard
    await query.edit_message_text(text=text, reply_markup=redeem_code_settings_keyboard(), parse_mode="HTML")
    await query.answer()


async def admin_redeem_set_threshold_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin to set low stock threshold."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "rc_set_threshold"
    repository = Repository(await get_db())
    current = await repository.get_setting("redeem_low_stock_threshold", 5)

    await query.edit_message_text(
        text=(
            f"⚙️ <b>Set Low Stock Threshold</b>\n\n"
            f"Current: <code>{current}</code>\n\n"
            "Send a number. When available codes drop below this, "
            "admins will be alerted.\n"
            "Example: <code>5</code>"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:rc_settings")]
        ]),
        parse_mode="HTML",
    )
    await query.answer()


async def admin_redeem_toggle_enabled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle redeem stock enabled/disabled."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("redeem_stock_enabled", True)
    await repository.update_setting("redeem_stock_enabled", not current)
    await query.answer(f"Redeem stock {'enabled ✅' if not current else 'disabled ❌'}!")
    await admin_redeem_settings_handler(update, context)


async def admin_redeem_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for redeem code settings."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("rc_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()
    repository = Repository(await get_db())

    if text.lower() == "/cancel":
        context.user_data.pop("admin_state", None)
        await admin_redeem_manager_handler(update, context)
        return

    if admin_state == "rc_set_threshold":
        try:
            val = int(text)
            if val < 0:
                raise ValueError
            await repository.update_setting("redeem_low_stock_threshold", val)
            await msg.reply_text(f"✅ Low stock threshold set to <code>{val}</code>.", parse_mode="HTML")
        except (ValueError, TypeError):
            await msg.reply_text("❌ Invalid number. Please send a positive integer.")
            return

    context.user_data.pop("admin_state", None)
    await admin_redeem_settings_handler(update, context)


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(admin_redeem_manager_handler, pattern="^admin:redeem_manager$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_add_code_start, pattern="^admin:rc_add_code$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_add_amt_handler, pattern=r"^admin:rc_add_amt:\d+\.?\d*$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_view_amount_handler, pattern=r"^admin:rc_view_amt:\d+\.?\d*:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_settings_handler, pattern="^admin:rc_settings$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_set_threshold_start, pattern="^admin:rc_set_threshold$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_toggle_enabled, pattern="^admin:rc_toggle$"))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_redeem_add_text_handler
    ), group=9)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_redeem_text_handler
    ), group=10)
