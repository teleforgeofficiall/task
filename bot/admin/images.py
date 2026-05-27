"""
images.py — Admin interface to customize visual banners (welcome, snap game, referral, etc.).
Allows swapping images via Telegram photo uploads or direct URL links.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import images_manager_keyboard

logger = logging.getLogger(__name__)


async def admin_images_manager_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show images manager menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())
    await repository.update_setting("_admin_pending_img", "")

    text = (
        "🖼️ <b>System Image Customizer</b>\n\n"
        "Configure custom graphic banners shown in the welcome, snap game, "
        "referral invite, and daily bonus sections of the bot."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=images_manager_keyboard(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_img_replace_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for new image banner."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    key = query.data.split(":")[2] # img_welcome / img_game etc.
    context.user_data["admin_state"] = f"replace_img_{key}"

    # Persist pending key in DB so it survives a --reload (user_data is wiped)
    repository = Repository(await get_db())
    await repository.update_setting("_admin_pending_img", key)

    text = (
        f"📸 <b>Replace Image: {key.replace('_', ' ').upper()}</b>\n\n"
        f"Please send the new image directly to this chat.\n\n"
        f"• You can upload a <b>photo file</b>.\n"
        f"• Alternatively, paste a direct <b>image URL</b> (e.g. Telegraph link)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:settings_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_images_receiver_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming photo or text URLs and updates DB settings."""
    msg = update.message or update.edited_message
    if not msg:
        logger.debug("No message in update")
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        logger.debug("Not an admin")
        return

    repository = Repository(await get_db())

    # Resolve the image key from user_data or DB
    admin_state = context.user_data.get("admin_state", "")
    key = None

    if admin_state.startswith("replace_img_"):
        key = admin_state.replace("replace_img_", "")
        context.user_data.pop("admin_state", None)
        logger.info("Using admin_state key: %s", key)
    else:
        key = await repository.get_setting("_admin_pending_img", "")
        if key:
            logger.info("Using DB fallback key: %s", key)

    if not key:
        return

    # Extract file_id from photo or URL from text
    file_id = None
    if msg.photo:
        file_id = msg.photo[-1].file_id
        logger.info("Extracted photo file_id for key %s", key)
    elif msg.text:
        text = msg.text.strip()
        if text.lower() == "/cancel":
            await repository.update_setting("_admin_pending_img", "")
            await msg.reply_text(
                "❌ Replacement cancelled.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")]
                ])
            )
            return
        if text.startswith("http://") or text.startswith("https://"):
            file_id = text
        else:
            await msg.reply_text("❌ Please upload a photo, or send a valid URL link.")
            return
    else:
        await msg.reply_text("❌ Unsupported message type. Please send a photo or text image link.")
        return

    # Save to DB
    await repository.update_setting(key, file_id)
    await repository.update_setting("_admin_pending_img", "")
    logger.info("Updated setting %s with new value", key)

    await msg.reply_text(
        f"✅ Banner image <b>{key.upper()}</b> successfully updated!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")]
        ])
    )


def register_handlers(application) -> None:
    """Register images admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_images_manager_handler, pattern="^admin:set_images$"))
    application.add_handler(CallbackQueryHandler(admin_img_replace_start, pattern="^admin:img_replace:[a-z_]+$"))
    
    # group=1 so it runs after group=0 and before other admin groups
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        admin_images_receiver_handler
    ), group=1)
