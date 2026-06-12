"""
start.py — Start command handler, force-subscribe verification, and main menu routing.
"""
from __future__ import annotations

import logging
import json
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import main_menu_keyboard
from bot.middlewares.auth import check_access
from bot.utils import edit_or_reply

logger = logging.getLogger(__name__)


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, repository: Repository) -> None:
    user = update.effective_user
    if not user:
        return

    passed = await check_access(update, context, repository)
    if not passed:
        return

    banner_url = await repository.get_image("img_welcome")
    start_text = await repository.get_setting(
        "start_message",
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>Welcome to TaskHub Rewards</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "> 💸 <b>Earn Real Money</b> by completing simple tasks, playing games & inviting friends.\n\n"
        "> ✨ <i>Trusted by thousands of active users daily.</i>\n"
        "> ⚡ <i>Fast withdrawals.</i>\n"
        "> 🔒 <i>Secure & automated payout system.</i>\n"
        "> 🎁 <i>Daily rewards, bonuses & referral income available.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 <b>What You Can Do Here:</b>\n"
        "• ✅ Complete Tasks & Earn\n"
        "• 🎮 Play Games & Win Rewards\n"
        "• 👥 Invite Friends for Lifetime Commission\n"
        "• 💰 Withdraw Directly to Your Wallet\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>💬 <i>\"Small earnings become big when consistency meets opportunity.\"</i></blockquote>\n\n"
        "🔥 <b>Start now</b> and turn your free time into real rewards.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ <i>Please avoid spam/fake activity. Our security system monitors all actions automatically.</i>\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = main_menu_keyboard()
    await edit_or_reply(
        update=update,
        context=context,
        text=start_text,
        reply_markup=kb,
        image_url=banner_url
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    repository = Repository(await get_db())
    user_id = user.id

    # Route /start verified to verified_start handler
    if context.args and context.args[0] == "verified":
        await verified_start(update, context)
        return

    db_user = await repository.get_user(user_id)
    if db_user:
        await repository.touch_user(user_id)
    else:
        referrer_id = None
        if context.args:
            arg = context.args[0]
            if arg.startswith("ref_"):
                try:
                    referrer_id = int(arg.split("_")[1])
                except (ValueError, IndexError):
                    pass

        if referrer_id:
            if referrer_id == user_id:
                referrer_id = None
            else:
                ref_user = await repository.get_user(referrer_id)
                if not ref_user or ref_user.banned:
                    referrer_id = None

        await repository.create_user(
            user_id=user_id,
            username=user.username,
            first_name=user.first_name,
            referrer=referrer_id
        )

    # Check device verification
    dev_verif_enabled = await repository.get_setting("device_verification_enabled", False)
    if dev_verif_enabled:
        db_user = await repository.get_user(user_id)
        if db_user and not db_user.device_verified:
            verif_url = await repository.get_setting("device_verification_url", "")
            if verif_url:
                bot_username = (await context.bot.get_me()).username or ""
                verify_url = f"{verif_url}/verify/{user_id}#bot={bot_username}"
                if verify_url.startswith("https://"):
                    btn = InlineKeyboardButton("🌐 Verify Device", web_app=WebAppInfo(url=verify_url))
                else:
                    btn = InlineKeyboardButton("🌐 Verify Device", url=verify_url)
                msg = await update.message.reply_text(
                    "<b>🔐 Device Verification Required</b>\n\n"
                    "<blockquote>To continue using this bot, you need to verify your device first. "
                    "This is a one-time security check to prevent abuse.</blockquote>\n\n"
                    "👇 <b>Tap the button below to start verification.</b>",
                    reply_markup=InlineKeyboardMarkup([[btn]]),
                    parse_mode="HTML"
                )
                context.user_data["verify_msg_id"] = msg.message_id
                await repository.update_setting(f"verify_msg:{user_id}", msg.message_id)
                return

    await send_main_menu(update, context, repository)


async def verified_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start verified — user came back from device verification page."""
    user = update.effective_user
    if not user:
        return
    repository = Repository(await get_db())
    db_user = await repository.get_user(user.id)
    if not db_user:
        # User doesn't exist yet, redirect to /start flow
        await start_command(update, context)
        return
    if not db_user.device_verified:
        # Re-check: maybe verification was completed but DB not refreshed
        db_user = await repository.get_user(user.id)
        if not db_user or not db_user.device_verified:
            await update.message.reply_text(
                "❌ <b>Device not verified yet.</b>\n\n"
                "Please complete device verification first.\n"
                "Use /start to try again.",
                parse_mode="HTML"
            )
            return
    # Delete the old verify message
    verify_msg_id = context.user_data.pop("verify_msg_id", None)
    if verify_msg_id:
        try:
            await context.bot.delete_message(chat_id=user.id, message_id=verify_msg_id)
        except Exception:
            pass

    await send_main_menu(update, context, repository)


async def menu_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    repository = Repository(await get_db())
    await send_main_menu(update, context, repository)


async def fsub_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    passed = await check_access(update, context, repository)
    if passed:
        await query.answer("✅ Verification successful!", show_alert=True)
        await send_main_menu(update, context, repository)
    else:
        await query.answer("❌ You still haven't joined all channels!", show_alert=True)


async def web_app_verified_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle web_app_data from device verification mini app (sendData + close)."""
    if not update.message or not update.message.web_app_data:
        return
    data = update.message.web_app_data
    try:
        payload = json.loads(data.data)
    except (json.JSONDecodeError, TypeError):
        return
    if payload.get("action") != "verified":
        return
    verify_msg_id = context.user_data.pop("verify_msg_id", None)
    if verify_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_user.id,
                message_id=verify_msg_id
            )
        except Exception:
            pass
    repository = Repository(await get_db())
    await send_main_menu(update, context, repository)


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("verified", verified_start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_verified_handler))
    application.add_handler(CallbackQueryHandler(menu_main_callback, pattern="^menu:main$"))
    application.add_handler(CallbackQueryHandler(fsub_verify_callback, pattern="^fsub:verify$"))
