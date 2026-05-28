"""
settings.py — Admin controls for general settings and message template customizations.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import settings_menu, messages_manager_keyboard
from bot.utils import escape_html

logger = logging.getLogger(__name__)


async def admin_settings_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings dashboard."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    repository = Repository(await get_db())
    refer_paused = await repository.get_setting("refer_paused", False)
    min_w = await repository.get_setting("min_withdraw", 10.0)
    max_w = await repository.get_setting("max_withdraw", 10000.0)
    bonus_val = await repository.get_setting("daily_bonus", 0.5)

    text = (
        f"⚙️ <b>TASKHUB Global Parameters</b>\n\n"
        f"💳 <b>Withdrawals:</b>\n"
        f"• Min limit: <code>₹{min_w:.2f}</code>\n"
        f"• Max limit: <code>₹{max_w:.2f}</code>\n\n"
        f"🎁 <b>Daily Reward:</b>\n"
        f"• Bonus credit: <code>₹{bonus_val:.2f}</code>\n\n"
        f"<i>Configure rules, forced subscribe flows, ads, banners, "
        f"and default UI messages below.</i>"
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=settings_menu(refer_paused=refer_paused),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await query.answer()


async def admin_settings_toggle_refer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle referral claim lock status."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("refer_paused", False)
    new_val = not current
    await repository.update_setting("refer_paused", new_val)
    
    status = "PAUSED" if new_val else "ACTIVE"
    await query.answer(f"Referral program is now {status}!")

    # Refresh
    await admin_settings_menu_handler(update, context)


async def admin_messages_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show customized messages menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "📝 <b>Custom Message Editor</b>\n\n"
        "Customize template copy and notifications sent by the bot. "
        "Support standard HTML styling tags (e.g. <code>&lt;b&gt;</code>, "
        "<code>&lt;code&gt;</code>, <code>&lt;blockquote&gt;</code>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=messages_manager_keyboard(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_msg_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for message content edits."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    key = query.data.split(":")[2] # start_message / launch_message / ban_message
    context.user_data["admin_state"] = f"edit_msg_{key}"

    repository = Repository(await get_db())
    current_val = await repository.get_setting(key, "")

    text = (
        f"📝 <b>Edit Template: {key.replace('_', ' ').upper()}</b>\n\n"
        f"Current text:\n"
        f"─────────────────────\n"
        f"{current_val}\n"
        f"─────────────────────\n\n"
        f"Please send the new formatted HTML text template.\n"
        f"<i>Type /cancel to abort.</i>"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:set_messages")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_settings_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming text template updates."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("edit_msg_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()
    repository = Repository(await get_db())

    key = admin_state.replace("edit_msg_", "")
    context.user_data.pop("admin_state", None)

    if text.lower() == "/cancel":
        await msg.reply_text("❌ Edit cancelled.", reply_markup=messages_manager_keyboard())
        return

    # Update template in DB
    await repository.update_setting(key, text)
    
    await msg.reply_text(
        f"✅ Template <b>{key.upper()}</b> successfully updated!",
        parse_mode="HTML",
        reply_markup=messages_manager_keyboard()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# RESET DATA
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_reset_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show reset data confirmation."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    await query.edit_message_text(
        text=(
            "⚠️ <b>Reset All Data</b>\n\n"
            "Are you sure? This will <b>permanently delete ALL</b> data:\n"
            "• All users, balances & history\n"
            "• All tasks & proofs\n"
            "• All withdrawals & transactions\n"
            "• All settings will reset to defaults\n\n"
            "<b>This action cannot be undone!</b>"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Reset Everything", callback_data="admin:reset_data_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:settings_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_reset_data_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute full database reset."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    from bot.database.session import reset_all_data

    try:
        await reset_all_data()
        await query.edit_message_text(
            "✅ <b>All data has been reset to factory defaults.</b>\n\n"
            "The bot is ready for fresh use.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Admin", callback_data="admin:main")]
            ]),
            parse_mode="HTML"
        )
        await query.answer("✅ Database reset complete!")
    except Exception as exc:
        logger.exception("Reset failed: %s", exc)
        await query.edit_message_text(
            f"❌ <b>Reset failed:</b> {escape_html(str(exc))}",
            parse_mode="HTML"
        )
        await query.answer("❌ Reset failed!")


def register_handlers(application) -> None:
    """Register settings admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_settings_menu_handler, pattern="^admin:settings_menu$"))
    application.add_handler(CallbackQueryHandler(admin_settings_toggle_refer, pattern="^admin:set_toggle_refer$"))
    application.add_handler(CallbackQueryHandler(admin_messages_menu_handler, pattern="^admin:set_messages$"))
    application.add_handler(CallbackQueryHandler(admin_msg_edit_start, pattern="^admin:msg_edit:[a-z_]+$"))
    application.add_handler(CallbackQueryHandler(admin_reset_data_start, pattern="^admin:reset_data$"))
    application.add_handler(CallbackQueryHandler(admin_reset_data_confirm, pattern="^admin:reset_data_confirm$"))
    
    # Text input handlers for updating templates
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_settings_text_handler
    ), group=2)
