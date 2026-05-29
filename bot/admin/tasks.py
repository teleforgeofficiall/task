"""
tasks.py — Admin creation, listing, pausing, and deleting tasks (both channel sub and manual).
Supports channel detail extraction from forwarded messages.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageOriginChannel, MessageOriginChat
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import tasks_menu, task_type_selection, task_action_keyboard, back_to_admin
from bot.utils import format_currency, escape_html

logger = logging.getLogger(__name__)


async def admin_tasks_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the admin tasks management menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    # Clean states
    context.user_data.pop("admin_state", None)

    text = (
        "💸 <b>Task Management</b>\n\n"
        "Create manual confirmation tasks or Telegram channel subscription tasks. "
        "Manage active tasks, toggle visibility, or review payouts."
    )

    await query.edit_message_text(text=text, reply_markup=tasks_menu(), parse_mode="HTML")
    await query.answer()


async def admin_task_add_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Select between manual and channel subscription tasks."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "➕ <b>Select Task Type</b>\n\n"
        "• <b>Manual Task:</b> Users read instructions and upload a screenshot/video proof for manual audit approval.\n"
        "• <b>Channel Task:</b> Users click a join link. The bot automatically verifies membership via API instantly."
    )

    await query.edit_message_text(text=text, reply_markup=task_type_selection(), parse_mode="HTML")
    await query.answer()


async def admin_task_create_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates task creation flow and prompts for description."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    task_type = query.data.split(":")[2] # manual / channel
    context.user_data["new_task_type"] = task_type
    context.user_data["admin_state"] = "awaiting_task_desc"

    text = (
        f"➕ <b>Create {task_type.upper()} Task — Step 1</b>\n\n"
        f"Please send the <b>description/title</b> of this task (e.g. <i>Join our Telegram Group</i> or <i>Like and Retweet our pinned post</i>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:tasks_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_tasks_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manage conversational steps for adding a new task."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("awaiting_task_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip() if msg.text else ""
    repository = Repository(await get_db())

    # Handle /cancel at any step
    if text.lower() == "/cancel":
        context.user_data.pop("admin_state", None)
        await msg.reply_text("❌ Cancelled.", reply_markup=back_to_admin())
        return

    # Allow /none only during image step; reject all other commands
    if text.startswith("/") and (text.lower() != "/none" or admin_state != "awaiting_task_image"):
        return

    # Step 1: Description
    if admin_state == "awaiting_task_desc":
        if not text:
            await msg.reply_text("❌ Description cannot be empty. Please send a text description.")
            return
        context.user_data["new_task_desc"] = text
        context.user_data["admin_state"] = "awaiting_task_guide"

        await msg.reply_text(
            "➕ <b>Create Task — Step 2</b>\n\n"
            "Please send the <b>guide instructions</b> telling the user exactly how to complete the task.\n\n"
            "<i>(For channel task, you can write something simple like 'Click Join and click Verify below')</i>",
            parse_mode="HTML"
        )
        return

    # Step 2: Guide
    if admin_state == "awaiting_task_guide":
        if not text:
            await msg.reply_text("❌ Guide instructions cannot be empty. Please send a text guide.")
            return
        context.user_data["new_task_guide"] = text
        context.user_data["admin_state"] = "awaiting_task_reward"

        await msg.reply_text(
            "➕ <b>Create Task — Step 3</b>\n\n"
            "Please send the payout <b>reward amount</b> in Rupees (e.g. <code>1.50</code> or <code>5</code>).",
            parse_mode="HTML"
        )
        return

    # Step 3: Reward
    if admin_state == "awaiting_task_reward":
        try:
            reward = float(text.replace(",", ""))
            if reward <= 0:
                raise ValueError()
        except ValueError:
            await msg.reply_text("❌ Invalid reward amount. Please send a positive decimal number.")
            return

        context.user_data["new_task_reward"] = reward
        task_type = context.user_data.get("new_task_type")

        if task_type == "manual":
            context.user_data["admin_state"] = "awaiting_task_image"
            await msg.reply_text(
                "➕ <b>Create Task — Step 4 (Optional Image)</b>\n\n"
                "Please upload/send a <b>guide image/banner</b> to display with this task.\n"
                "Or send <code>/none</code> to skip this and use the default system image.",
                parse_mode="HTML"
            )
        else:
            # Channel tasks
            context.user_data["admin_state"] = "awaiting_task_channel"
            await msg.reply_text(
                "➕ <b>Create Channel Task — Step 4 (Link Channel)</b>\n\n"
                "👉 Please <b>FORWARD</b> a message from the target Telegram channel directly into this chat.\n\n"
                "<i>(The bot will automatically extract the channel ID and link from the forwarded message! "
                "Ensure the bot is added as an administrator in that channel first.)</i>\n\n"
                "Alternatively, send the info manually in this format:\n"
                "<code>channel_id|channel_url|channel_title</code>\n"
                "e.g. <code>-100123456789|https://t.me/my_channel|Official Channel</code>",
                parse_mode="HTML"
            )
        return

    # Step 4: Image/Video (Manual Task)
    if admin_state == "awaiting_task_image":
        file_id = ""
        media_type = "photo"

        if msg.photo:
            file_id = msg.photo[-1].file_id
            media_type = "photo"
        elif msg.video:
            file_id = msg.video.file_id
            media_type = "video"
        elif msg.document and msg.document.mime_type:
            mime = msg.document.mime_type.lower()
            if mime.startswith("image/"):
                file_id = msg.document.file_id
                media_type = "photo"
            elif mime.startswith("video/"):
                file_id = msg.document.file_id
                media_type = "video"
            else:
                await msg.reply_text("❌ Please upload a photo or video, or send /none to skip.")
                return
        elif text and text.lower() == "/none":
            file_id = ""
            media_type = "photo"
        else:
            await msg.reply_text("❌ Please upload a photo or video, or send /none to skip.")
            return

        # Commit task to database
        task_data = {
            "task_type": "manual",
            "description": context.user_data["new_task_desc"],
            "guide": context.user_data["new_task_guide"],
            "reward": context.user_data["new_task_reward"],
            "image": file_id,
            "media_type": media_type,
            "is_active": True
        }

        # Clear memory
        context.user_data.pop("admin_state", None)
        context.user_data.pop("new_task_type", None)
        context.user_data.pop("new_task_desc", None)
        context.user_data.pop("new_task_guide", None)
        context.user_data.pop("new_task_reward", None)

        task = await repository.create_task(task_data)
        await msg.reply_text(
            f"✅ <b>Manual Task Created Successfully!</b>\n\n"
            f"• <b>Task ID:</b> <code>#{task.id}</code>\n"
            f"• <b>Title:</b> {escape_html(task.description)}\n"
            f"• <b>Reward:</b> {format_currency(task.reward)}",
            parse_mode="HTML",
            reply_markup=tasks_menu()
        )
        return

    # Step 4: Channel Verification details (Channel Task)
    if admin_state == "awaiting_task_channel":
        chan_id = None
        chan_url = None
        chan_title = None

        # Check forwarded message
        if msg.forward_origin and isinstance(msg.forward_origin, (MessageOriginChannel, MessageOriginChat)):
            chat = msg.forward_origin.chat if isinstance(msg.forward_origin, MessageOriginChannel) else msg.forward_origin.sender_chat
            if chat.type == "channel":
                chan_id = str(chat.id)
                chan_title = chat.title
                if chat.username:
                    chan_url = f"https://t.me/{chat.username}"
                else:
                    # Look for invite link in user_data or request manually
                    await msg.reply_text(
                        "⚠️ Forwarded successfully, but channel is private (no username).\n"
                        "Please send the public invite link URL for this channel so users can join."
                    )
                    context.user_data["fwd_channel_id"] = chan_id
                    context.user_data["fwd_channel_title"] = chan_title
                    context.user_data["admin_state"] = "awaiting_task_channel_url"
                    return
            else:
                await msg.reply_text("❌ Forwarded chat is not a channel. Please forward from a channel.")
                return
        else:
            # Parse text input manually
            parts = text.split("|")
            if len(parts) == 3:
                chan_id = parts[0].strip()
                chan_url = parts[1].strip()
                chan_title = parts[2].strip()
            else:
                await msg.reply_text("❌ Invalid format. Please forward a channel message or send in correct format.")
                return

        # Save and create task
        await save_channel_task(update, context, repository, chan_id, chan_url, chan_title)


async def admin_task_channel_url_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Extra step to receive channel URL for private/username-less forwarded channels."""
    admin_state = context.user_data.get("admin_state", "")
    if admin_state != "awaiting_task_channel_url":
        return

    msg = update.message
    url = msg.text.strip()
    if not url.startswith("https://"):
        await msg.reply_text("❌ Please send a valid channel join URL starting with https://")
        return

    repository = Repository(await get_db())
    chan_id = context.user_data.pop("fwd_channel_id")
    chan_title = context.user_data.pop("fwd_channel_title")
    context.user_data.pop("admin_state", None)

    await save_channel_task(update, context, repository, chan_id, url, chan_title)


async def save_channel_task(update: Update, context: ContextTypes.DEFAULT_TYPE, repository: Repository, chan_id: str, chan_url: str, chan_title: str) -> None:
    """Commit the channel subscription task details to MongoDB."""
    task_data = {
        "task_type": "channel",
        "description": context.user_data["new_task_desc"],
        "guide": context.user_data["new_task_guide"],
        "reward": context.user_data["new_task_reward"],
        "channel_id": chan_id,
        "channel_url": chan_url,
        "channel_title": chan_title,
        "is_active": True
    }

    # Clear memory
    context.user_data.pop("new_task_type", None)
    context.user_data.pop("new_task_desc", None)
    context.user_data.pop("new_task_guide", None)
    context.user_data.pop("new_task_reward", None)

    task = await repository.create_task(task_data)
    await update.message.reply_text(
        f"✅ <b>Channel Task Created!</b>\n\n"
        f"• <b>Task ID:</b> <code>#{task.id}</code>\n"
        f"• <b>Title:</b> {escape_html(task.description)}\n"
        f"• <b>Target Channel:</b> {escape_html(task.channel_title)} (ID: <code>{task.channel_id}</code>)\n"
        f"• <b>Reward:</b> {format_currency(task.reward)}",
        parse_mode="HTML",
        reply_markup=tasks_menu()
    )


async def admin_tasks_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active/paused tasks with page limits."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())
    tasks = await repository.get_all_tasks()

    if not tasks:
        await query.answer("No tasks created yet.", show_alert=True)
        return

    per_page = 5
    total_pages = (len(tasks) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_tasks = tasks[start_idx:end_idx]

    keyboard = []
    for t in page_tasks:
        state_icon = "🟢" if t.is_active else "⏸️"
        keyboard.append([
            InlineKeyboardButton(f"{state_icon} #{t.id}: {t.description[:25]}", callback_data=f"admin:task_view:{t.id}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:tasks_list:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:tasks_list:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Tasks", callback_data="admin:tasks_menu")])

    text = (
        f"📋 <b>TASKHUB Task Manager (Page {page+1}/{total_pages})</b>\n\n"
        f"🟢 = Task is active/viewable by users.\n"
        f"⏸️ = Task is paused/hidden from users."
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_task_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View options for a specific task."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    task_id = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    task = await repository.get_task(task_id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    status = "🟢 ACTIVE (Showing to users)" if task.is_active else "⏸️ PAUSED (Hidden from users)"
    
    chan_info = ""
    if task.task_type == "channel":
        chan_info = (
            f"📢 <b>Target Channel:</b> {escape_html(task.channel_title)}\n"
            f"└ <b>Channel ID:</b> <code>{task.channel_id}</code>\n"
            f"└ <b>Url:</b> {task.channel_url}\n"
        )

    text = (
        f"📋 <b>Task Information</b>\n"
        f"─────────────────────\n"
        f"• <b>Task ID:</b> <code>#{task.id}</code>\n"
        f"• <b>Type:</b> <code>{task.task_type.upper()}</code>\n"
        f"• <b>Status:</b> {status}\n"
        f"• <b>Reward:</b> <code>{format_currency(task.reward)}</code>\n\n"
        f"• <b>Title:</b> {escape_html(task.description)}\n"
        f"• <b>Guide:</b> <i>{escape_html(task.guide)}</i>\n"
        f"{chan_info}"
        f"─────────────────────"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=task_action_keyboard(task.id, task.is_active, page),
        parse_mode="HTML"
    )


async def admin_task_toggle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause or resume a task."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    task_id = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    new_state = await repository.toggle_task(task_id)
    
    state_txt = "resumed" if new_state else "paused"
    await query.answer(f"Task #{task_id} successfully {state_txt}!")

    # Refresh task view
    query.data = f"admin:task_view:{task_id}:{page}"
    await admin_task_view_handler(update, context)


async def admin_task_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a task."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    task_id = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    await repository.delete_task(task_id)
    await query.answer(f"Task #{task_id} deleted successfully!")

    # Return to list
    query.data = f"admin:tasks_list:{page}"
    await admin_tasks_list_handler(update, context)


def register_handlers(application) -> None:
    """Register tasks admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_tasks_menu_handler, pattern="^admin:tasks_menu$"))
    application.add_handler(CallbackQueryHandler(admin_task_add_type_handler, pattern="^admin:task_add_type$"))
    application.add_handler(CallbackQueryHandler(admin_task_create_start, pattern="^admin:task_create:(manual|channel)$"))
    application.add_handler(CallbackQueryHandler(admin_tasks_list_handler, pattern="^admin:tasks_list:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_task_view_handler, pattern="^admin:task_view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_task_toggle_handler, pattern="^admin:task_toggle:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_task_delete_handler, pattern="^admin:task_del:\d+:\d+$"))
    
    # Text and media input handlers for creating task details
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        admin_tasks_text_input_handler
    ), group=14)
    # Custom URLs handler for private channels fsub creation
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_task_channel_url_handler
    ), group=15)
