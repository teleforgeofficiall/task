"""
withdrawals.py — Admin workflows to approve and reject user withdrawal requests.
Refunds balances automatically on rejection and supports custom notes.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import withdraws_menu, withdrawal_action_keyboard
from bot.services.notifications import notify_user
from bot.utils import format_currency, escape_html

logger = logging.getLogger(__name__)


async def admin_withdraws_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show withdrawals menu with live pending counts."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    pending = await repository.get_pending_withdrawals()
    upi_count = sum(1 for w in pending if w.get("method") == "upi")
    stars_count = sum(1 for w in pending if w.get("method") == "stars")

    text = (
        "💳 <b>Withdrawal Payouts Manager</b>\n\n"
        "Audit pending withdrawal requests. Approve to mark them as paid, "
        "or reject to automatically refund the debit amount back to the user's wallet."
    )

    await query.edit_message_text(text=text, reply_markup=withdraws_menu(upi_count, stars_count), parse_mode="HTML")
    await query.answer()


async def admin_withdraws_queue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending withdrawals (paginated)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    pending = await repository.get_pending_withdrawals()
    if not pending:
        await query.answer("🎉 No pending withdrawals remaining!", show_alert=True)
        return

    per_page = 5
    total_pages = (len(pending) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_wd = pending[start_idx:end_idx]

    keyboard = []
    for w in page_wd:
        wid = w["id"]
        uid = w["user_id"]
        amt = w["amount"]
        keyboard.append([
            InlineKeyboardButton(f"💳 Request #{wid} — User {uid} (₹{amt})", callback_data=f"admin:wd_view:{wid}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:withdraws_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:withdraws_queue:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:withdraws_menu")])

    text = (
        f"💳 <b>Pending Payouts Queue (Page {page+1}/{total_pages})</b>\n\n"
        f"There are currently <code>{len(pending)}</code> pending payouts awaiting review."
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def admin_wd_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View details of a specific withdrawal request."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    wid = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await query.answer("Withdrawal not found or already processed.", show_alert=True)
        return

    user = await repository.get_user(w["user_id"])
    user_name = user.first_name if user else "Unknown User"
    trust_score = max(0, min(100, 100 - user.fraud_score)) if user else 100

    text = (
        f"💳 <b>Withdrawal Request — ID: #{wid}</b>\n"
        f"─────────────────────\n"
        f"👤 <b>User:</b> {escape_html(user_name)} (ID: <code>{w['user_id']}</code>)\n"
        f"🛡️ <b>Trust Score:</b> <code>{trust_score}%</code> (Fraud score: {user.fraud_score if user else 0})\n"
        f"💰 <b>Payout Amount:</b> <b>{format_currency(w['amount'])}</b>\n"
        f"📱 <b>UPI ID Target:</b> <code>{w['upi_id']}</code>\n"
        f"📅 <b>Submitted:</b> <code>{w['date'].split('T')[0]}</code>\n"
        f"─────────────────────\n"
        f"<i>Please verify user legitimacy before confirming payouts.</i>"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=withdrawal_action_keyboard(wid, page),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_wd_decision_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm payment or reject and refund withdrawal requests."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    decision = parts[2] # approve / reject
    wid = int(parts[3])
    page = int(parts[4])

    repository = Repository(await get_db())
    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await query.answer("Withdrawal already processed.", show_alert=True)
        return

    admin_id = query.from_user.id
    user_id = w["user_id"]
    amount = w["amount"]
    upi = w["upi_id"]

    if decision == "approve":
        # 1. Update status
        await repository.update_withdrawal_status(wid, "paid", admin_id)
        # 2. Notify user
        await notify_user(
            bot=context.bot,
            user_id=user_id,
            text=(
                f"✅ <b>Withdrawal Dispatched!</b>\n\n"
                f"Your withdrawal request <b>#{wid}</b> for <b>{format_currency(amount)}</b> has been approved.\n"
                f"Funds have been successfully dispatched to your UPI: <code>{upi}</code>."
            )
        )
        await query.answer("Withdrawal marked paid & user notified!")
    else:
        # Refund withdrawal
        # 1. Update status
        reason = "Rejected by administration."
        await repository.update_withdrawal_status(wid, "rejected", admin_id, reason)
        # 2. Refund wallet balance
        await repository.credit_balance(
            user_id=user_id,
            amount=amount,
            tx_type="withdrawal_refund",
            description=f"Refund for rejected withdrawal request #{wid}",
            ref_id=str(wid)
        )
        # 3. Notify user
        await notify_user(
            bot=context.bot,
            user_id=user_id,
            text=(
                f"❌ <b>Withdrawal Request Rejected!</b>\n\n"
                f"Your request <b>#{wid}</b> for <b>{format_currency(amount)}</b> was rejected.\n"
                f"Reason: <i>{reason}</i>\n"
                f"Your funds have been refunded back to your wallet."
            )
        )
        await query.answer("Withdrawal rejected & balance refunded!")

    # Refresh queue
    await send_withdrawal_queue_panel(query.from_user.id, page, context, repository)


async def admin_wd_custom_reason_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for custom withdrawal rejection reason."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    wid = int(parts[2])
    page = int(parts[3])

    context.user_data["admin_state"] = f"reject_wd_{wid}_{page}"

    await query.edit_message_text(
        text=(
            "❌ <b>Reject Payout — Custom Reason</b>\n\n"
            "Please send the reason why this withdrawal is being rejected. "
            "The user will be refunded automatically and notified with your feedback."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin:wd_view:{wid}:{page}")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_withdrawals_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming text for custom withdrawal rejection reason (UPI + Stars)."""
    if context.user_data is None:
        return
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("reject_wd_") and not admin_state.startswith("reject_star_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    parts = admin_state.split("_")
    wid = int(parts[2])
    page = int(parts[3])

    is_star = admin_state.startswith("reject_star_")
    context.user_data.pop("admin_state", None)
    reason = update.message.text.strip()
    repository = Repository(await get_db())

    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await update.message.reply_text("❌ Withdrawal already processed.")
        return

    # Reject & refund
    await repository.update_withdrawal_status(wid, "rejected", user_id, reason)
    await repository.credit_balance(
        user_id=w["user_id"],
        amount=w["amount"],
        tx_type="withdrawal_refund",
        description=f"Refund for rejected withdrawal request #{wid}",
        ref_id=str(wid)
    )

    # Notify user
    await notify_user(
        bot=context.bot,
        user_id=w["user_id"],
        text=(
            f"❌ <b>Withdrawal Request Rejected!</b>\n\n"
            f"Your request <b>#{wid}</b> for <b>{format_currency(w['amount'])}</b> was rejected.\n"
            f"Reason: <i>{escape_html(reason)}</i>\n"
            f"Your funds have been refunded back to your wallet."
        )
    )

    await update.message.reply_text("✅ Withdrawal rejected and balance refunded successfully.")
    if is_star:
        await send_star_queue_panel(user_id, page, context, repository)
    else:
        await send_withdrawal_queue_panel(user_id, page, context, repository)


async def send_withdrawal_queue_panel(admin_id: int, page: int, context, repository: Repository) -> None:
    """Internal helper to recreate and send the pending withdrawals menu."""
    pending = await repository.get_pending_withdrawals()
    if not pending:
        await context.bot.send_message(
            chat_id=admin_id,
            text="🎉 <b>No pending withdrawals remaining!</b>",
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
    page_wd = pending[start_idx:end_idx]

    keyboard = []
    for w in page_wd:
        wid = w["id"]
        uid = w["user_id"]
        amt = w["amount"]
        keyboard.append([
            InlineKeyboardButton(f"💳 Request #{wid} — User {uid} (₹{amt})", callback_data=f"admin:wd_view:{wid}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:withdraws_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:withdraws_queue:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:withdraws_menu")])

    await context.bot.send_message(
        chat_id=admin_id,
        text=(
            f"💳 <b>Pending Payouts Queue (Page {page+1}/{total_pages})</b>\n\n"
            f"There are currently <code>{len(pending)}</code> pending payouts awaiting review."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# (Redeem code queue removed — now instant via inventory system)


# ═══════════════════════════════════════════════════════════════════════════════
# STAR WITHDRAWAL ADMIN HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_stars_queue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending star withdrawals (paginated)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    pending = await repository.get_pending_star_withdrawals()
    if not pending:
        await query.answer("🎉 No pending star withdrawals!", show_alert=True)
        return

    per_page = 5
    total_pages = (len(pending) + per_page - 1) // per_page

    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_wd = pending[start_idx:end_idx]

    keyboard = []
    for w in page_wd:
        wid = w["id"]
        uid = w["user_id"]
        stars = w.get("stars", 0)
        keyboard.append([
            InlineKeyboardButton(f"⭐ Star #{wid} — User {uid} ({stars}⭐)", callback_data=f"admin:star_view:{wid}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:stars_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:stars_queue:{page+1}"))

    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:withdraws_menu")])

    text = (
        f"⭐ <b>Pending Star Withdrawals (Page {page+1}/{total_pages})</b>\n\n"
        f"There are currently <code>{len(pending)}</code> pending star withdrawals."
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def admin_star_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View details of a specific star withdrawal."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    wid = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending" or w.get("method") != "stars":
        await query.answer("Star withdrawal not found or already processed.", show_alert=True)
        return

    user = await repository.get_user(w["user_id"])
    user_name = user.first_name if user else "Unknown User"
    stars = w.get("stars", 0)
    channel_link = w.get("channel_link", "")

    text = (
        f"⭐ <b>Star Withdrawal — ID: #{wid}</b>\n"
        f"─────────────────────\n"
        f"👤 <b>User:</b> {escape_html(user_name)} (ID: <code>{w['user_id']}</code>)\n"
        f"⭐ <b>Stars:</b> <code>{stars}⭐</code>\n"
        f"💰 <b>Amount:</b> <b>{format_currency(w['amount'])}</b>\n"
        f"📅 <b>Submitted:</b> <code>{w['date'].split('T')[0]}</code>\n\n"
        f"📍 <b>React Here:</b>\n"
        f"<code>{channel_link}</code>\n"
        f"─────────────────────\n"
        f"<i>Go to the channel post, add ⭐ reactions, then approve below.</i>"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Open Post", url=channel_link)],
    ]
    from bot.keyboards.admin_kb import star_withdrawal_action_keyboard
    action_kb = star_withdrawal_action_keyboard(wid, page).inline_keyboard
    keyboard.extend(action_kb)

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_star_decision_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve or reject a star withdrawal."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    decision = parts[2]  # approve / reject
    wid = int(parts[3])
    page = int(parts[4])

    repository = Repository(await get_db())
    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await query.answer("Star withdrawal already processed.", show_alert=True)
        return

    admin_id = query.from_user.id
    user_id = w["user_id"]
    amount = w["amount"]
    stars = w.get("stars", 0)

    if decision == "approve":
        await repository.update_withdrawal_status(wid, "paid", admin_id)
        await notify_user(
            bot=context.bot,
            user_id=user_id,
            text=(
                f"✅ <b>Stars Withdrawal Approved!</b>\n\n"
                f"Your withdrawal request <b>#{wid}</b> for "
                f"<b>{stars}⭐ ({format_currency(amount)})</b> has been approved.\n"
                f"⭐ Admin has reacted on your post. Thank you for using TASKHUB!"
            )
        )
        await query.answer("Star withdrawal marked paid & user notified!")
    else:
        reason = "Rejected by administration."
        await repository.update_withdrawal_status(wid, "rejected", admin_id, reason)
        await repository.credit_balance(
            user_id=user_id, amount=amount,
            tx_type="withdrawal_refund",
            description=f"Refund for rejected star withdrawal #{wid}",
            ref_id=str(wid)
        )
        await notify_user(
            bot=context.bot,
            user_id=user_id,
            text=(
                f"❌ <b>Stars Withdrawal Rejected!</b>\n\n"
                f"Your request <b>#{wid}</b> for "
                f"<b>{stars}⭐ ({format_currency(amount)})</b> was rejected.\n"
                f"Reason: <i>{reason}</i>\n"
                f"Your funds have been refunded back to your wallet."
            )
        )
        await query.answer("Star withdrawal rejected & balance refunded!")

    # Delete the withdrawal detail message
    try:
        await query.message.delete()
    except Exception:
        pass

    await send_star_queue_panel(query.from_user.id, page, context, repository)


async def admin_star_custom_reason_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for custom star withdrawal rejection reason."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    wid = int(parts[2])
    page = int(parts[3])

    context.user_data["admin_state"] = f"reject_star_{wid}_{page}"

    await query.edit_message_text(
        text=(
            "❌ <b>Reject Star Withdrawal — Custom Reason</b>\n\n"
            "Please send the reason why this star withdrawal is being rejected. "
            "The user will be refunded automatically and notified with your feedback."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin:star_view:{wid}:{page}")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def send_star_queue_panel(admin_id: int, page: int, context, repository: Repository) -> None:
    """Internal helper to recreate and send the pending star withdrawals menu."""
    pending = await repository.get_pending_star_withdrawals()
    if not pending:
        await context.bot.send_message(
            chat_id=admin_id,
            text="🎉 <b>No pending star withdrawals remaining!</b>",
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
    page_wd = pending[start_idx:end_idx]

    keyboard = []
    for w in page_wd:
        wid = w["id"]
        uid = w["user_id"]
        stars = w.get("stars", 0)
        keyboard.append([
            InlineKeyboardButton(f"⭐ Star #{wid} — User {uid} ({stars}⭐)", callback_data=f"admin:star_view:{wid}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:stars_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:stars_queue:{page+1}"))

    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:withdraws_menu")])

    await context.bot.send_message(
        chat_id=admin_id,
        text=(
            f"⭐ <b>Pending Star Withdrawals (Page {page+1}/{total_pages})</b>\n\n"
            f"There are currently <code>{len(pending)}</code> pending star withdrawals."
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


def register_handlers(application) -> None:
    """Register withdrawal admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_withdraws_menu_handler, pattern="^admin:withdraws_menu$"))
    application.add_handler(CallbackQueryHandler(admin_withdraws_queue_handler, pattern="^admin:withdraws_queue:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_wd_view_handler, pattern="^admin:wd_view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_wd_decision_handler, pattern="^admin:wd_decide:(approve|reject):\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_wd_custom_reason_start, pattern="^admin:wd_reason:\d+:\d+$"))

    # Star withdrawal admin handlers
    application.add_handler(CallbackQueryHandler(admin_stars_queue_handler, pattern="^admin:stars_queue:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_star_view_handler, pattern="^admin:star_view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_star_decision_handler, pattern="^admin:star_decide:(approve|reject):\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_star_custom_reason_start, pattern="^admin:star_reason:\d+:\d+$"))

    # Text input handlers for custom rejection reasons (UPI + Star)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_withdrawals_text_handler
    ), group=7)


