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
    query = update.callback_query
    if not query:
        return

    context.user_data.pop("state", None)

    try:
        page = int(query.data.split(":")[2])
    except (IndexError, ValueError):
        page = 0

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("Profile not found.")
        return

    active_tasks = await repository.get_active_tasks()
    todo_tasks = [t for t in active_tasks if t.id not in user.completed_tasks]

    if not todo_tasks:
        no_tasks_text = (
            "📋 <b>Available Tasks</b>\n\n"
            "<blockquote>Amazing! You have completed all available tasks.\n"
            "Check back later for new tasks, or refer friends to keep earning!</blockquote>"
        )
        banner_url = await repository.get_image("img_tasks_list")
        await edit_or_reply(
            update=update,
            context=context,
            text=no_tasks_text,
            reply_markup=back_to_menu_keyboard(),
            image_url=banner_url
        )
        return

    per_page = 5
    total_pages = (len(todo_tasks) + per_page - 1) // per_page

    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_tasks = todo_tasks[start_idx:end_idx]

    tasks_data = [{"id": t.id, "description": t.description, "reward": t.reward} for t in page_tasks]

    tasks_text = (
        f"📋 <b>Active Tasks</b> — Page {page+1}/{total_pages}\n\n"
        f"<blockquote>Tap a task below to view instructions and submit verification.</blockquote>"
    )

    banner_url = await repository.get_image("img_tasks_list")
    await edit_or_reply(
        update=update,
        context=context,
        text=tasks_text,
        reply_markup=tasks_list_keyboard(tasks_data, page, total_pages),
        image_url=banner_url
    )


async def task_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await query.answer("Task not found.", show_alert=True)
        return

    is_pending = await repository.has_pending_proof(user_id, task_id)
    pending_badge = " (Proof Pending Review)" if is_pending else ""

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

    if is_pending and task.task_type == "manual":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Back to List", callback_data=f"menu:tasks:{page}")]
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

    try:
        repository = Repository(await get_db())
    except Exception as e:
        logger.error(f"Failed to get DB for task verify: {e}")
        try:
            await query.answer("Database error. Please try again later.", show_alert=True)
        except Exception:
            pass
        return

    user_id = query.from_user.id

    try:
        task = await repository.get_task(task_id)
    except Exception as e:
        logger.error(f"Failed to get task #{task_id}: {e}")
        try:
            await query.answer("An error occurred while processing this task.", show_alert=True)
        except Exception:
            pass
        return

    if not task or task.task_type != "channel":
        try:
            await query.answer("Invalid channel task.", show_alert=True)
        except Exception:
            pass
        return

    # Prevent duplicate claims - check if user already completed this task
    try:
        user = await repository.get_user(user_id)
        if user and task.id in (user.completed_tasks or []):
            await query.answer("You have already completed this task!", show_alert=True)
            return
    except Exception as e:
        logger.error(f"Failed to check duplicate task completion: {e}")

    try:
        # Check join status
        joined = await check_channel_membership(context.bot, user_id, task.channel_id)
        if not joined:
            try:
                await query.answer("You must join the channel before verification.", show_alert=True)
            except Exception:
                pass
            return

        # Credit reward instantly
        await repository.credit_balance(
            user_id=user_id,
            amount=task.reward,
            tx_type="task_reward",
            description=f"Completed Channel Task #{task.id}",
            ref_id=str(task.id)
        )

        # Mark task as completed in DB
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
                await s.execute(
                    _update(_UserTable)
                    .where(_UserTable.user_id == user_id)
                    .values(completed_tasks=c)
                )
                await s.commit()
        except Exception as e:
            logger.error(f"SQLAlchemy update failed for task #{task_id}: {e}")

        try:
            await query.answer("Reward Credited!", show_alert=True)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Failed to verify channel task: {e}")
        try:
            await query.answer("An unexpected error occurred.", show_alert=True)
        except Exception:
            pass

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
    query = update.callback_query
    if not query:
        return

    data_parts = query.data.split(":")
    task_id = int(data_parts[2])
    page = int(data_parts[3])

    context.user_data["state"] = f"awaiting_proof_{task_id}_{page}"

    text = (
        "📸 <b>Submit Task Proof</b>\n\n"
        "<blockquote>Please send a screenshot or screen recording verifying "
        "you completed the instructions.\n\n"
        "Send the media directly in this chat. Tap <b>Cancel</b> below to abort.</blockquote>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Cancel", callback_data=f"task:view:{task_id}:{page}")]
    ])

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=kb
    )


async def proof_receiver_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.user_data.get("state", "")
    if not state.startswith("awaiting_proof_"):
        return

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
    elif msg.document and msg.document.mime_type:
        mime = msg.document.mime_type.lower()
        if mime.startswith("image/"):
            file_id = msg.document.file_id
            file_type = "photo"
        elif mime.startswith("video/"):
            file_id = msg.document.file_id
            file_type = "video"

    if not file_id:
        await msg.reply_text(
            "Invalid file type!\n"
            "Please upload a valid screenshot (photo) or video recording proving task completion.",
            parse_mode="HTML"
        )
        return

    repository = Repository(await get_db())

    await repository.add_proof(
        user_id=user_id,
        task_id=task_id,
        file_id=file_id,
        file_type=file_type
    )

    context.user_data.pop("state", None)

    await msg.reply_text(
        "✅ <b>Proof Submitted!</b>\n\n"
        "<blockquote>Our team will review your submission. "
        "Once approved, your reward will be credited to your wallet instantly.</blockquote>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Tasks", callback_data=f"menu:tasks:{page}")]
        ])
    )


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(tasks_menu_handler, pattern="^menu:tasks:\d+$"))
    application.add_handler(CallbackQueryHandler(task_view_handler, pattern="^task:view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(task_verify_channel_handler, pattern="^task:verify_channel:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(task_submit_proof_handler, pattern="^task:submit_proof:\d+:\d+$"))

    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        proof_receiver_handler
    ))
