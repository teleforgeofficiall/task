from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.utils import escape_html

logger = logging.getLogger(__name__)


async def earn_more_manager_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    context.user_data.pop("admin_edit_id", None)
    context.user_data.pop("admin_temp_name", None)

    repository = Repository(await get_db())
    items = await repository.get_earn_more_items()

    text = "<b>💰 Earn More Manager</b>\n\n"
    if not items:
        text += "No earn items configured yet.\nTap <b>Add Earn</b> to create one."
    else:
        text += f"Total items: {len(items)}\n\n"
        for i, item in enumerate(items, 1):
            price = item.get("price", 0.0)
            text += f"{i}. {escape_html(item['button_name'])} — ₹{price:.2f}\n"

    keyboard = []
    if items:
        for item in items:
            price = item.get("price", 0.0)
            keyboard.append([
                InlineKeyboardButton(f"✏️ {escape_html(item['button_name'])} — ₹{price:.2f}", callback_data=f"admin:earn_more_edit:{item['id']}"),
                InlineKeyboardButton(f"🗑️", callback_data=f"admin:earn_more_del:{item['id']}"),
            ])
    keyboard.append([InlineKeyboardButton("➕ Add Earn", callback_data="admin:earn_more_add")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")])

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def earn_more_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_earn_more_name"
    context.user_data.pop("admin_edit_id", None)
    context.user_data.pop("admin_temp_name", None)

    await query.edit_message_text(
        text="💰 <b>Add Earn — Step 1/3</b>\n\nSend the <b>button name</b> jo users ko dikhega (e.g., Telegram Channel, Website, etc.):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:earn_more_mgmt")]
        ]),
        parse_mode="HTML",
    )
    await query.answer()


async def earn_more_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    data = query.data.split(":")
    item_id = int(data[-1])

    repository = Repository(await get_db())
    items = await repository.get_earn_more_items()
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        await query.answer("Item not found.", show_alert=True)
        return

    context.user_data["admin_state"] = "awaiting_earn_more_name"
    context.user_data["admin_edit_id"] = item_id
    context.user_data["admin_temp_name"] = None

    await query.edit_message_text(
        text=(
            f"💰 <b>Edit Earn — Step 1/3</b>\n\n"
            f"Current button name: {escape_html(item['button_name'])}\n"
            f"Current price: ₹{item.get('price', 0):.2f}\n\n"
            f"Send the <b>new button name</b> (or same to keep):"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:earn_more_mgmt")]
        ]),
        parse_mode="HTML",
    )
    await query.answer()


async def earn_more_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    data = query.data.split(":")
    item_id = int(data[-1])

    repository = Repository(await get_db())
    await repository.delete_earn_more_item(item_id)

    await query.answer("✅ Item deleted.", show_alert=True)
    # Refresh manager menu
    await earn_more_manager_handler(update, context)


async def earn_more_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        admin_state = context.user_data.get("admin_state", "")
        if not admin_state.startswith("awaiting_earn_more_"):
            return

        user_id = update.effective_user.id
        if not is_admin(user_id):
            return

        msg = update.message
        if not msg:
            return

        repository = Repository(await get_db())
        edit_id = context.user_data.get("admin_edit_id")
        is_edit = edit_id is not None

        if admin_state == "awaiting_earn_more_name":
            if not msg.text:
                await msg.reply_text("❌ Please send a text message for the button name.")
                return
            text = msg.text.strip()
            context.user_data["admin_temp_name"] = text
            context.user_data["admin_state"] = "awaiting_earn_more_price"

            step_label = "Edit" if is_edit else "Add"
            await msg.reply_text(
                f"💰 <b>{step_label} Earn — Step 2/3</b>\n\n"
                f"Button name: {escape_html(text)}\n\n"
                f"Send the <b>price/reward amount</b> for this item (e.g. <code>5.00</code>).\n"
                f"Send <code>0</code> if it's free.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="admin:earn_more_mgmt")]
                ]),
                parse_mode="HTML",
            )
            return

        if admin_state == "awaiting_earn_more_price":
            if not msg.text:
                await msg.reply_text("❌ Please send a numeric price (e.g. <code>5.00</code>).")
                return
            try:
                price = float(msg.text.strip().replace(",", ""))
                if price < 0:
                    raise ValueError()
            except ValueError:
                await msg.reply_text("❌ Invalid price. Please send a positive number (e.g. <code>2.50</code>).")
                return
            context.user_data["admin_temp_price"] = price
            context.user_data["admin_state"] = "awaiting_earn_more_content"

            step_label = "Edit" if is_edit else "Add"
            button_name = context.user_data.get("admin_temp_name", "")
            await msg.reply_text(
                f"💰 <b>{step_label} Earn — Step 3/3</b>\n\n"
                f"Button name: {escape_html(button_name)}\n"
                f"Price: ₹{price:.2f}\n\n"
                f"Now send your full message description / image / video (ya koi bhi message forward karein):",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Cancel", callback_data="admin:earn_more_mgmt")]
                ]),
                parse_mode="HTML",
            )
            return

        if admin_state == "awaiting_earn_more_content":
            button_name = context.user_data.get("admin_temp_name", "")
            price = context.user_data.get("admin_temp_price", 0.0)
            if not button_name:
                await msg.reply_text("❌ Session expired. Please start again.")
                context.user_data.pop("admin_state", None)
                return

            msg_type = "text"
            msg_content = ""
            if msg.text:
                msg_type = "text"
                msg_content = msg.text_html or msg.text
            elif msg.photo:
                msg_type = "photo"
                msg_content = msg.photo[-1].file_id
                if msg.caption:
                    msg_content += "|||" + msg.caption_html
            elif msg.video:
                msg_type = "video"
                msg_content = msg.video.file_id
                if msg.caption:
                    msg_content += "|||" + msg.caption_html
            else:
                await msg.reply_text("❌ Unsupported message type. Please send text, photo, or video.")
                return

            if is_edit:
                await repository.update_earn_more_item(edit_id, button_name=button_name, price=price, msg_type=msg_type, msg_content=msg_content)
            else:
                await repository.add_earn_more_item(button_name, msg_type, msg_content, price=price)

            context.user_data.pop("admin_state", None)
            context.user_data.pop("admin_edit_id", None)
            context.user_data.pop("admin_temp_name", None)
            context.user_data.pop("admin_temp_price", None)

            action = "updated" if is_edit else "added"
            await msg.reply_text(
                f"✅ <b>Earn More item {action}!</b>\n\n"
                f"• Button Name: {escape_html(button_name)}\n"
                f"• Price: ₹{price:.2f}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Manager", callback_data="admin:earn_more_mgmt")]
                ]),
                parse_mode="HTML",
            )
    except Exception as e:
        logger.exception("Error in earn_more_message_handler: %s", e)
        try:
            await update.message.reply_text(f"❌ Error: {e}")
        except Exception:
            pass


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(earn_more_manager_handler, pattern="^admin:earn_more_mgmt$"))
    application.add_handler(CallbackQueryHandler(earn_more_add, pattern="^admin:earn_more_add$"))
    application.add_handler(CallbackQueryHandler(earn_more_edit, pattern=r"^admin:earn_more_edit:\d+$"))
    application.add_handler(CallbackQueryHandler(earn_more_delete, pattern=r"^admin:earn_more_del:\d+$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, earn_more_message_handler), group=13)
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, earn_more_message_handler), group=13)
