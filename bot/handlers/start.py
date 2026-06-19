"""
start.py — Start command handler, force-subscribe verification, device verification,
and congrats + MiniApp flow.
"""
from __future__ import annotations

import logging
import json
import time
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import main_menu_keyboard, miniapp_keyboard
from bot.middlewares.auth import check_access
from bot.utils import edit_or_reply

logger = logging.getLogger(__name__)


async def send_congrats(update: Update, context: ContextTypes.DEFAULT_TYPE, repository: Repository) -> None:
    """Send congrats message with MiniApp button after all checks pass."""
    user = update.effective_user
    if not user:
        return

    miniapp_url = await repository.get_setting("miniapp_url", "https://taskhub-khaki.vercel.app")
    separator = "&" if "?" in miniapp_url else "?"
    miniapp_url = f"{miniapp_url}{separator}_cb={int(time.time())}"
    congrats_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🎉 <b>Congratulations!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Welcome to <b>TaskHub</b>! You now have full access.\n\n"
        "Open the MiniApp below to start earning:\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💸 Complete Tasks & Earn\n"
        "🎮 Play Games & Win\n"
        "👥 Refer Friends for Commission\n"
        "💰 Withdraw to UPI / Stars\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = miniapp_keyboard(miniapp_url)
    await edit_or_reply(
        update=update,
        context=context,
        text=congrats_text,
        reply_markup=kb,
        parse_mode="HTML"
    )


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
                    parts = arg.split("_")
                    referrer_id = int(parts[1])
                    if len(parts) >= 4 and parts[2] == "task":
                        task_ref = int(parts[3])
                        context.user_data["referred_task"] = task_ref
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

    # STEP 1: Check force-subscribe channels
    passed = await check_access(update, context, repository)
    if not passed:
        return

    # STEP 2: Check device verification
    dev_verif_enabled = await repository.get_setting("device_verification_enabled", False)
    if dev_verif_enabled:
        db_user = await repository.get_user(user_id)
        if db_user and not db_user.device_verified:
            verif_url = await repository.get_setting("device_verification_url", "")
            if verif_url:
                bot_username = (await context.bot.get_me()).username or ""
                if verif_url.endswith("/device.html"):
                    base_url = verif_url
                else:
                    base_url = f"{verif_url.rstrip('/')}/device.html"
                sep = "&" if "?" in base_url else "?"
                verify_url = f"{base_url}{sep}user_id={user_id}"
                if base_url.startswith("https://"):
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

    # STEP 3: All passed — send congrats + MiniApp button
    await send_congrats(update, context, repository)


async def verified_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start verified — user came back from device verification page."""
    user = update.effective_user
    if not user:
        return
    repository = Repository(await get_db())
    db_user = await repository.get_user(user.id)
    if not db_user:
        await start_command(update, context)
        return
    if not db_user.device_verified:
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

    await send_congrats(update, context, repository)


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
        await query.answer("✅ All channels joined!", show_alert=True)

        # After fsub passes, check device verification
        user_id = query.from_user.id
        dev_verif_enabled = await repository.get_setting("device_verification_enabled", False)
        if dev_verif_enabled:
            db_user = await repository.get_user(user_id)
            if db_user and not db_user.device_verified:
                verif_url = await repository.get_setting("device_verification_url", "")
                if verif_url:
                    bot_username = (await context.bot.get_me()).username or ""
                    if verif_url.endswith("/device.html"):
                        base_url = verif_url
                    else:
                        base_url = f"{verif_url.rstrip('/')}/device.html"
                    sep = "&" if "?" in base_url else "?"
                    verify_url = f"{base_url}{sep}user_id={user_id}"
                    if base_url.startswith("https://"):
                        btn = InlineKeyboardButton("🌐 Verify Device", web_app=WebAppInfo(url=verify_url))
                    else:
                        btn = InlineKeyboardButton("🌐 Verify Device", url=verify_url)
                    await query.message.delete()
                    msg = await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "<b>🔐 Device Verification Required</b>\n\n"
                            "<blockquote>To continue using this bot, you need to verify your device first. "
                            "This is a one-time security check to prevent abuse.</blockquote>\n\n"
                            "👇 <b>Tap the button below to start verification.</b>"
                        ),
                        reply_markup=InlineKeyboardMarkup([[btn]]),
                        parse_mode="HTML"
                    )
                    context.user_data["verify_msg_id"] = msg.message_id
                    return

        # No device verification needed — go to congrats
        await query.message.delete()
        await send_congrats(update, context, repository)
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

    repository = Repository(await get_db())
    action = payload.get("action")

    if action == "verified":
        await repository.update_user_fields(update.effective_user.id, device_verified=True)

        verify_msg_id = context.user_data.pop("verify_msg_id", None)
        if verify_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_user.id,
                    message_id=verify_msg_id
                )
            except Exception:
                pass

        await send_congrats(update, context, repository)

    elif action == "failed":
        warning_text = (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ <b>Security Alert</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Your device could not be verified.\n\n"
            "Multiple accounts or VPN usage is not allowed. "
            "Each user is only allowed one account.\n\n"
            "If you believe this is an error, please contact support."
        )
        verify_msg_id = context.user_data.pop("verify_msg_id", None)
        if verify_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_user.id,
                    message_id=verify_msg_id,
                    text=warning_text,
                    parse_mode="HTML"
                )
            except Exception:
                await edit_or_reply(
                    update=update,
                    context=context,
                    text=warning_text,
                    parse_mode="HTML"
                )
        else:
            await edit_or_reply(
                update=update,
                context=context,
                text=warning_text,
                parse_mode="HTML"
            )


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("verified", verified_start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_verified_handler))
    application.add_handler(CallbackQueryHandler(menu_main_callback, pattern="^menu:main$"))
    application.add_handler(CallbackQueryHandler(fsub_verify_callback, pattern="^fsub:verify$"))
