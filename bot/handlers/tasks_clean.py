"""
tasks.py ??? Task browsing, membership checks for channel tasks, and proof submission flow for manual tasks.
"""
from __future__ import annotations

import logging
from sqlalchemy import select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.keyboards.user_kb import tasks_list_keyboard, task_detail_keyboard, back_to_menu_keyboard
from bot.middlewares.auth import check_channel_membership
from bot.services.notifications import notify_user
from bot.services.referral import check_referral_success
from bot.utils import edit_or_reply, format_currency, escape_html

logger = logging.getLogger(__name__)


async def tasks_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Browse active tasks (paginated). Hides fully completed tasks."""
    query = update.callback_query
    if not query:
        return

    # Clear state in case user was in the middle of proof submission
    context.user_data.pop("state", None)

    try:
        page = int(query.data.split(":")[2])
    except (IndexError, ValueError):
        page = 0

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("??? Profile not found.")
        return

    # Fetch active tasks and filter out completed ones
    active_tasks = await repository.get_active_tasks()
    todo_tasks = [t for t in active_tasks if t.id not in user.completed_tasks]

    if not todo_tasks:
        no_tasks_text = (
            "???? <b>Available Tasks</b>\n\n"
            "<blockquote>???? <b>Amazing! You have completed all available tasks.</b>\n"
            "Check back later for new tasks, or refer friends to keep earning!</blockquote>"
        )
        banner_url = await repository.get_image("img_treasure")
        await edit_or_reply(
            update=update,
            context=context,
            text=no_tasks_text,
            reply_markup=back_to_menu_keyboard(),
            image_url=banner_url
        )
        return

    # Pagination
    per_page = 5
    total_pages = (len(todo_tasks) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_tasks = todo_tasks[start_idx:end_idx]

    # Map database tasks to dictionaries for keyboards
    tasks_data = [{"id": t.id, "description": t.description, "reward": t.reward} for t in page_tasks]
    
    tasks_text = (
        f"???? <b>Earn Balance ??? Active Tasks (Page {page+1}/{total_pages})</b>\n\n"
        f"<blockquote>Select a task from the list below to read instructions and submit verification. "
        f"Rewards are credited instantly for channel joins, and upon review for manual tasks.</blockquote>"
    )

    banner_url = await repository.get_image("img_treasure")
    await edit_or_reply(
        update=update,
        context=context,
        text=tasks_text,
        reply_markup=tasks_list_keyboard(tasks_data, page, total_pages),
        image_url=banner_url
    )


async def task_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View details of a specific task."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split(":")
    task_id = int(data_parts[2])
    page = int(data_parts[3])

    repository = Repository(await get_db())
    user_id = query.from_user.id

    task = await repository.get_task(task_id)
    if not task:
        await query.answer("??? Task not found.", show_alert=True)
        return

    is_pending = await repository.has_pending_proof(user_id, task_id)
    pending_badge = " ⏳ <i>Proof Pending Review</i>" if is_pending else ""

    text = (
        f"📋 <b>Task Details</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<blockquote><b>Description:</b> {escape_html(task.description)}</blockquote>\n\n"
        f"💰 <b>Reward:</b> <code>{format_currency(task.reward)}</code>{pending_badge}\n\n"
        f"📝 <b>Guide / Instructions</b>\n"
        f"<blockquote>{escape_html(task.guide)}</blockquote>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = task_detail_keyboard(
        task_id=task.id,
        task_type=task.task_type,
        url=task.channel_url or "",
        page=page
    )

    # If proof is already pending, remove the submission option from keyboard
    if is_pending and task.task_type == "manual":
        # Keep back button only
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("???? Back to List", callback_data=f"menu:tasks:{page}")]
        ])

    banner_url = task.image or await repository.get_image("img_channel_task")
    media_type = task.media_type if task.image else "photo"
    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=kb,
        image_url=banner_url,
        media_type=media_type
    )


async def task_verify_channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Instant verification for channel subscription tasks."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split(":")
    task_id = int(data_parts[2])
    page = int(data_parts[3])

    repository = Repository(await get_db())
    user_id = query.from_user.id

    try:
        task = await repository.get_task(task_id)
    except Exception as e:
        logger.error(f"Failed to get task #{task_id}: {e}")
        await query.answer("??? An error occurred while processing this task.", show_alert=True)
        return

    if not task or task.task_type != "channel":
        await query.answer("??? Invalid channel task.", show_alert=True)
        return

    try:
        # Check join status
        joined = await check_channel_membership(context.bot, user_id, task.channel_id)
        if not joined:
            await query.answer("??? You must join the channel before verification.", show_alert=True)
            return

        # Credit reward instantly
        await repository.credit_balance(
            user_id=user_id,
            amount=task.reward,
            tx_type="task_reward",
            description=f"Completed Channel Task #{task.id}",
            ref_id=str(task.id)
        )

        # Mark task as completed
        try:
            from sqlalchemy import update as _update
            from bot.database.models_sql import UserTable as _UserTable
            s = await repository._session()
            u_row = await s.execute(select(_UserTable).where(_UserTable.user_id == user_id))
            u = u_row.scalar_one_or_none()
            if u:
                c = list(u.completed_tasks or [])
                if task.id not in c:
                    c.append(task.id)
                await s.execute(_update(_UserTable).where(_UserTable.user_id == user_id).values(completed_tasks=c))
                await s.commit()
        except Exception as e:
            logger.error(f"SQLAlchemy update failed: {e}")
            # Continue anyway - task reward was already credited

        await query.answer("???? Reward Credited!", show_alert=True)
        
    except Exception as e:
        logger.error(f"Failed to verify channel task: {e}")
        await query.answer("??? An unexpected error occurred.", show_alert=True)

    # Check if referral reward unlocks
    try:
        await check_referral_success(repository, user_id, context.bot)
    except Exception as e:
        logger.error(f"Referral check failed: {e}")

    # Return to task menu
    try:
        query.data = f"menu:tasks:{page}"
        await tasks_menu_handler(update, context)
    except Exception as e:
        logger.error(f"Failed to refresh task menu: {e}")


async def task_submit_proof_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiate proof submission state for manual tasks."""
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split(":")
    task_id = int(data_parts[2])
    page = int(data_parts[3])

    # Save state in user_data
    context.user_data["state"] = f"awaiting_proof_{task_id}_{page}"

    text = (
        "???? <b>Submit Task Proof</b>\n\n"
        "<blockquote>Please send the screenshot or screen recording verifying "
        "you completed the instructions.</blockquote>\n\n"
        "<i>Send the media directly into this chat. Tap Cancel below to abort.</i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("??? Cancel", callback_data=f"task:view:{task_id}:{page}")]
    ])

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=kb
    )


async def proof_receiver_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Message handler to receive photos/videos when state is awaiting_proof."""
    state = context.user_data.get("state", "")
    if not state.startswith("awaiting_proof_"):
        return

    # Parse task_id and page from state
    parts = state.split("_")
    task_id = int(parts[2])
    page = int(parts[3])

    user_id = update.effective_user.id
    msg = update.message
    file_id = None
    file_type = None

    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
    elif msg.document and msg.document.mime_type.startswith(("image/", "video/")):
        file_id = msg.document.file_id
        file_type = "photo" if msg.document.mime_type.startswith("image/") else "video"

    if not file_id:
        await msg.reply_text(
            "?????? <b>Invalid file type!</b>\n"
            "Please upload a valid screenshot (photo) or video recording proving task completion.",
            parse_mode="HTML"
        )
        return

    repository = Repository(await get_db())
    
    # Save proof to DB
    await repository.add_proof(
        user_id=user_id,
        task_id=task_id,
        file_id=file_id,
        file_type=file_type
    )

    # Clear state
    context.user_data.pop("state", None)

    # Send confirmation
    await msg.reply_text(
        "??? <b>Proof submitted successfully!</b>\n\n"
        "<blockquote>Our team will review your proof. Once approved, your reward will be credited to your wallet.</blockquote>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("???? Back to Tasks", callback_data=f"menu:tasks:{page}")]
        ])
    )


def register_handlers(application) -> None:
    """Register task handlers."""
    application.add_handler(CallbackQueryHandler(tasks_menu_handler, pattern="^menu:tasks:\d+$"))
    application.add_handler(CallbackQueryHandler(task_view_handler, pattern="^task:view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(task_verify_channel_handler, pattern="^task:verify_channel:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(task_submit_proof_handler, pattern="^task:submit_proof:\d+:\d+$"))
    
    # Message handler for receiving proof (runs only when active state matches)
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        proof_receiver_handler
    ))


