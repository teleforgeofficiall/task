from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.constants import ParseMode

from bot.database import get_db, Repository
from bot.keyboards.user_kb import back_to_menu_keyboard, main_menu_keyboard
from bot.utils import edit_or_reply
from bot.middlewares.auth import check_access

logger = logging.getLogger(__name__)


async def earn_more_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    items = await repository.get_earn_more_items()

    if not items:
        text = "💰 <b>Earn More</b>\n\nNo earn opportunities available right now. Check back later!"
        await edit_or_reply(update=update, context=context, text=text, reply_markup=back_to_menu_keyboard())
        return

    text = "💰 <b>Earn More</b>\n\nBrowse available opportunities below and earn rewards by completing tasks."

    keyboard = []
    for item in items:
        price = item.get("price", 0.0)
        label = f"{item['button_name']} — Only ₹{price:.2f}" if price else item['button_name']
        keyboard.append([InlineKeyboardButton(label, callback_data=f"earn_more:show:{item['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")])

    await edit_or_reply(update=update, context=context, text=text, reply_markup=InlineKeyboardMarkup(keyboard))


async def earn_more_show_content(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = query.data.split(":")
    item_id = int(data[-1])

    repository = Repository(await get_db())
    items = await repository.get_earn_more_items()
    item = next((i for i in items if i["id"] == item_id), None)

    if not item:
        await query.answer("Item not found.", show_alert=True)
        return

    msg_type = item.get("msg_type", "text")
    msg_content = item.get("msg_content", "")

    if not msg_content:
        await query.answer("No content configured.", show_alert=True)
        return

    caption = ""
    content = msg_content
    if msg_type in ("photo", "video") and "|||" in msg_content:
        parts = msg_content.split("|||", 1)
        content = parts[0]
        caption = parts[1]

    back_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Earn More", callback_data="menu:earn_more")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")],
    ])

    if msg_type == "text":
        await edit_or_reply(update=update, context=context, text=msg_content, reply_markup=back_kb)
    elif msg_type == "photo":
        await query.message.delete()
        await query.message.reply_photo(photo=content, caption=caption or None, parse_mode="HTML", reply_markup=back_kb)
    elif msg_type == "video":
        await query.message.delete()
        await query.message.reply_video(video=content, caption=caption or None, parse_mode="HTML", reply_markup=back_kb)


async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    repository = Repository(await get_db())

    passed = await check_access(update, context, repository)
    if not passed:
        return

    text = (
        "📢 <b>ADVERTISE WITH TASKHUB</b>\n\n"
        "<blockquote>Promote Your Channel, App, Website or Business</blockquote>\n\n"
        "✨ <b>Features</b>\n"
        "<blockquote>"
        "👥 Get More Members & Visitors\n"
        "📱 Promote Telegram Channels & Apps\n"
        "🌐 Website Promotion Available\n"
        "⚡ Fast Approval & Delivery\n"
        "💎 Trusted Promotion Platform"
        "</blockquote>\n\n"
        "<blockquote>🚀 <b>Grow Your Audience With Taskhub Promotion Services</b></blockquote>\n\n"
        "📩 <b>Contact Admin For Promotion</b>\n"
        "<blockquote>"
        "📧 <b>Email:</b> <code>kanhaojha726@gmail.com</code>\n"
        "✈️ <b>Telegram:</b> <a href=\"https://t.me/x_kanha_007\">@x_kanha_007</a>"
        "</blockquote>"
    )

    banner_url = await repository.get_image("img_promote")
    if banner_url:
        try:
            await update.message.reply_photo(
                photo=banner_url,
                caption=text,
                reply_markup=main_menu_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return
        except Exception as exc:
            logger.warning("Failed to send promote banner photo (%s); falling back to text.", exc)

    await update.message.reply_text(
        text=text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(earn_more_handler, pattern="^menu:earn_more$"))
    application.add_handler(CallbackQueryHandler(earn_more_show_content, pattern=r"^earn_more:show:\d+$"))
    application.add_handler(CommandHandler("promote", promote_command))
