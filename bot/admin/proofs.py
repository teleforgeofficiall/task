"""
proofs.py — Admin workflows to inspect, approve, and reject user-submitted manual task proofs.
Includes batch-processing, custom rejection reasons, and automatic referral evaluations.
"""
from __future__ import annotations

import base64
import io
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import proofs_menu, proof_review_keyboard
from bot.services.notifications import notify_user
from bot.services.referral import check_referral_success
from bot.utils import format_currency, escape_html

logger = logging.getLogger(__name__)


async def admin_proofs_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show proofs menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "📝 <b>Task Proof Audits</b>\n\n"
        "Inspect screenshot uploads or video screen recordings from users. "
        "Approve valid completions to credit wallet balances, or reject fraudulent submissions."
    )

    await query.edit_message_text(text=text, reply_markup=proofs_menu(), parse_mode="HTML")
    await query.answer()


async def admin_proofs_queue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending proofs (paginated)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    pending = await repository.get_pending_proofs()
    if not pending:
        await query.answer("🎉 No pending task proofs to review!", show_alert=True)
        return

    per_page = 5
    total_pages = (len(pending) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_proofs = pending[start_idx:end_idx]

    keyboard = []
    for p in page_proofs:
        p_id = p["id"]
        uid = p["user_id"]
        t_id = p["task_id"]
        keyboard.append([
            InlineKeyboardButton(f"📝 Proof #{p_id} — User {uid} (Task #{t_id})", callback_data=f"admin:proof_view:{p_id}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:proofs_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:proofs_queue:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:proofs_menu")])

    text = (
        f"📝 <b>Pending Proofs Queue (Page {page+1}/{total_pages})</b>\n\n"
        f"There are currently <code>{len(pending)}</code> pending submissions awaiting audit."
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


async def admin_proof_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inspect proof media and details."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    proof_id = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    proof = await repository.get_proof(proof_id)
    if not proof or proof["status"] != "pending":
        await query.answer("Proof not found or already processed.", show_alert=True)
        return

    task = await repository.get_task(proof["task_id"])
    task_title = task.description if task else f"Task #{proof['task_id']}"
    reward = task.reward if task else 0.0

    caption = (
        f"📝 <b>Proof Audit — ID: #{proof_id}</b>\n"
        f"─────────────────────\n"
        f"👤 <b>User:</b> ID <code>{proof['user_id']}</code>\n"
        f"💸 <b>Task:</b> {escape_html(task_title)} (ID: #{proof['task_id']})\n"
        f"💰 <b>Reward:</b> <code>{format_currency(reward)}</code>\n"
        f"📅 <b>Submitted:</b> <code>{proof['date'].split('T')[0]}</code>\n"
        f"─────────────────────\n"
        f"<i>Inspect the attached media and select an action below.</i>"
    )

    # We must display the media. Since editing text into a media message isn't directly allowed
    # if the previous message was text-only, we delete the panel and send a new photo/video message.
    file_id = proof["proof_file_id"]
    file_type = proof.get("file_type", "photo")
    kb = proof_review_keyboard(proof_id, page)

    # Delete inline admin control message
    try:
        await query.delete_message()
    except Exception:
        pass

    # Helper to send media, handling base64 data URLs
    async def _send_media():
        if file_id and file_id.startswith('data:'):
            # Base64 data URL — decode and send as file upload
            try:
                _header, encoded = file_id.split(',', 1)
                bytes_data = base64.b64decode(encoded)
                buf = io.BytesIO(bytes_data)
                buf.seek(0)
                if file_type == "video":
                    await context.bot.send_video(
                        chat_id=query.from_user.id, video=buf,
                        caption=caption, reply_markup=kb, parse_mode="HTML",
                        filename="proof." + ("mp4" if file_type == "video" else "jpg")
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=query.from_user.id, photo=buf,
                        caption=caption, reply_markup=kb, parse_mode="HTML"
                    )
                return True
            except Exception as exc:
                logger.error("Failed to send proof base64 data: %s", exc)
                return False
        try:
            if file_type == "video":
                await context.bot.send_video(
                    chat_id=query.from_user.id, video=file_id,
                    caption=caption, reply_markup=kb, parse_mode="HTML"
                )
            else:
                await context.bot.send_photo(
                    chat_id=query.from_user.id, photo=file_id,
                    caption=caption, reply_markup=kb, parse_mode="HTML"
                )
            return True
        except Exception:
            return False

    sent = await _send_media()
    if not sent:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"{caption}\n\n⚠️ <i>Failed to load media. File was stored as base64 data URL.</i>",
            reply_markup=kb,
            parse_mode="HTML"
        )


async def admin_proof_decision_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve or reject a proof with standard settings."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    decision = parts[2] # approve / reject
    proof_id = int(parts[3])
    page = int(parts[4])

    repository = Repository(await get_db())
    proof = await repository.get_proof(proof_id)
    if not proof or proof["status"] != "pending":
        await query.answer("Proof already processed.", show_alert=True)
        return

    admin_id = query.from_user.id
    user_id = proof["user_id"]
    task_id = proof["task_id"]
    task = await repository.get_task(task_id)
    reward = task.reward if task else 0.0

    if decision == "approve":
        # 1. Update status
        await repository.update_proof_status(proof_id, "approved", admin_id)
        # 2. Add to user completed tasks
        from sqlalchemy import update as _update, select
        from bot.database.models_sql import UserTable as _UserTable
        s = await repository._session()
        u_row = await s.execute(select(_UserTable).where(_UserTable.user_id == user_id))
        u = u_row.scalar_one_or_none()
        if u:
            c = list(u.completed_tasks or [])
            if task_id not in c:
                c.append(task_id)
            await s.execute(_update(_UserTable).where(_UserTable.user_id == user_id).values(completed_tasks=c))
            await s.commit()
        # 3. Credit wallet balance
        await repository.credit_balance(
            user_id=user_id,
            amount=reward,
            tx_type="task_reward",
            description=f"Completed Task #{task_id}: {task.description if task else ''}",
            ref_id=str(task_id)
        )
        # 4. Increment task completion count
        try:
            await repository.increment_task_completion(task_id)
        except Exception as e:
            logger.error(f"Failed to increment task completion count: {e}")

        # 5. Notify user
        await notify_user(
            bot=context.bot,
            user_id=user_id,
            text=(
                f"🎉 <b>Task Proof Approved!</b>\n\n"
                f"Your submission for task <b>{task.description if task else task_id}</b> has been approved.\n"
                f"Credited: <b>{format_currency(reward)}</b> to your wallet balance."
            )
        )
        await query.answer("Approved & credited successfully!")
        
        # 5. Check if referral reward unlocks
        await check_referral_success(repository, user_id, context.bot)

    else:
        # Default rejection reason
        reason = "Proof does not match task instructions."
        await repository.update_proof_status(proof_id, "rejected", admin_id, reason)
        
        # Notify user
        await notify_user(
            bot=context.bot,
            user_id=user_id,
            text=(
                f"❌ <b>Task Proof Rejected!</b>\n\n"
                f"Your submission for task <b>{task.description if task else task_id}</b> was rejected by admins.\n"
                f"Reason: <i>{reason}</i>"
            )
        )
        await query.answer("Rejected submission successfully.")

    # Re-send queue panel
    await send_queue_panel(query.from_user.id, page, context, repository)


async def admin_proof_custom_reason_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for custom rejection reason."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    proof_id = int(parts[2])
    page = int(parts[3])

    context.user_data["admin_state"] = f"reject_proof_{proof_id}_{page}"

    try:
        await query.delete_message()
    except Exception:
        pass

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "❌ <b>Custom Rejection Reason</b>\n\n"
            "Please send the reason why this task proof is being rejected.\n"
            "The user will receive this message as feedback."
        ),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_proofs_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming text for custom rejection reason."""
    if context.user_data is None:
        return
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("reject_proof_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    parts = admin_state.split("_")
    proof_id = int(parts[2])
    page = int(parts[3])

    context.user_data.pop("admin_state", None)
    reason = update.message.text.strip()
    repository = Repository(await get_db())

    proof = await repository.get_proof(proof_id)
    if not proof or proof["status"] != "pending":
        await update.message.reply_text("❌ Proof already processed.")
        return

    task = await repository.get_task(proof["task_id"])

    await repository.update_proof_status(proof_id, "rejected", user_id, reason)
    
    # Notify user
    await notify_user(
        bot=context.bot,
        user_id=proof["user_id"],
        text=(
            f"❌ <b>Task Proof Rejected!</b>\n\n"
            f"Your submission for task <b>{task.description if task else proof['task_id']}</b> was rejected by admins.\n"
            f"Reason: <i>{escape_html(reason)}</i>"
        )
    )

    await update.message.reply_text("✅ Proof rejected with custom reason successfully.")
    await send_queue_panel(user_id, page, context, repository)


async def send_queue_panel(admin_id: int, page: int, context, repository: Repository) -> None:
    """Internal helper to recreate and send the pending queue menu to admin."""
    pending = await repository.get_pending_proofs()
    if not pending:
        await context.bot.send_message(
            chat_id=admin_id,
            text="🎉 <b>No pending task proofs remaining!</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
            ]),
            parse_mode="HTML"
        )
        return

    per_page = 5
    total_pages = (len(pending) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_proofs = pending[start_idx:end_idx]

    keyboard = []
    for p in page_proofs:
        p_id = p["id"]
        uid = p["user_id"]
        t_id = p["task_id"]
        keyboard.append([
            InlineKeyboardButton(f"📝 Proof #{p_id} — User {uid} (Task #{t_id})", callback_data=f"admin:proof_view:{p_id}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:proofs_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:proofs_queue:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:proofs_menu")])

    await context.bot.send_message(
        chat_id=admin_id,
        text=(
            f"📝 <b>Pending Proofs Queue (Page {page+1}/{total_pages})</b>\n\n"
            f"There are currently <code>{len(pending)}</code> pending submissions awaiting audit."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


def register_handlers(application) -> None:
    """Register proofs admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_proofs_menu_handler, pattern="^admin:proofs_menu$"))
    application.add_handler(CallbackQueryHandler(admin_proofs_queue_handler, pattern="^admin:proofs_queue:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_proof_view_handler, pattern="^admin:proof_view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_proof_decision_handler, pattern="^admin:proof_decide:(approve|reject):\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_proof_custom_reason_start, pattern="^admin:proof_reason:\d+:\d+$"))
    
    # Text input handlers for custom rejection reasons
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_proofs_text_handler
    ), group=16)
