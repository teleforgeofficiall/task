"""
start.py — Start command handler, force-subscribe verification, and main menu routing.
"""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

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
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>Welcome to TaskHub!</b>\n\n"
        "> Complete tasks, invite friends, and earn real money.\n"
        "> Instant payouts — 100% secure.\n"
        "━━━━━━━━━━━━━━━━━━━━"
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


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(menu_main_callback, pattern="^menu:main$"))
    application.add_handler(CallbackQueryHandler(fsub_verify_callback, pattern="^fsub:verify$"))
