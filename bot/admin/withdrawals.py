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
    """Show withdrawals menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "💳 <b>Withdrawal Payouts Manager</b>\n\n"
        "Audit pending UPI withdrawal requests. Approve to mark them as paid, "
        "or reject to automatically refund the debit amount back to the user's wallet."
    )

    await query.edit_message_text(text=text, reply_markup=withdraws_menu(), parse_mode="HTML")
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
    """Process incoming text for custom withdrawal rejection reason."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("reject_wd_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    parts = admin_state.split("_")
    wid = int(parts[2])
    page = int(parts[3])

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


# ═══════════════════════════════════════════════════════════════════════════════
# REDEEM CODE ADMIN HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_redeems_queue_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List pending redeem code requests (paginated)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    pending = await repository.get_pending_redeems()
    if not pending:
        await query.answer("🎉 No pending redeem code requests!", show_alert=True)
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
            InlineKeyboardButton(f"🎫 Redeem #{wid} — User {uid} (₹{amt})", callback_data=f"admin:redeem_view:{wid}:{page}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:redeems_queue:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:redeems_queue:{page+1}"))

    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:withdraws_menu")])

    text = (
        f"🎫 <b>Pending Redeem Code Queue (Page {page+1}/{total_pages})</b>\n\n"
        f"There are currently <code>{len(pending)}</code> pending redeem requests."
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await query.answer()


async def admin_redeem_view_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View a specific redeem request and pay with code."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    wid = int(parts[2])
    page = int(parts[3])

    repository = Repository(await get_db())
    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending" or w.get("method") != "redeem":
        await query.answer("Redeem request not found or already processed.", show_alert=True)
        return

    user = await repository.get_user(w["user_id"])
    user_name = user.first_name if user else "Unknown"

    text = (
        f"🎫 <b>Redeem Code Request — #{wid}</b>\n"
        f"─────────────────────\n"
        f"👤 <b>User:</b> {escape_html(user_name)} (ID: <code>{w['user_id']}</code>)\n"
        f"💰 <b>Amount:</b> <b>{format_currency(w['amount'])}</b>\n"
        f"📅 <b>Submitted:</b> <code>{w['date'].split('T')[0]}</code>\n"
        f"─────────────────────\n"
        f"<i>Send a redeem code to this user upon payment.</i>"
    )

    keyboard = [
        [InlineKeyboardButton("💳 Pay — Enter Code", callback_data=f"admin:redeem_pay:{wid}:{page}"),
         InlineKeyboardButton("👤 User Profile", callback_data=f"admin:usr_profile_{w['user_id']}")],
        [InlineKeyboardButton("❌ Reject & Refund", callback_data=f"admin:wd_decide:reject:{wid}:{page}"),
         InlineKeyboardButton("🔙 Back", callback_data=f"admin:redeems_queue:{page}")],
    ]

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_redeem_pay_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for redeem code to send to user."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    wid = int(parts[2])
    page = int(parts[3])

    context.user_data["admin_state"] = f"redeem_pay_{wid}_{page}"

    await query.edit_message_text(
        text=(
            "🎫 <b>Pay with Redeem Code</b>\n\n"
            "Send the <b>redeem code</b> you want to give to this user.\n"
            "The code will be sent to the user and the request will be marked as paid.\n\n"
            "<i>Type /cancel to abort.</i>"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin:redeem_view:{wid}:{page}")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_redeem_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process admin redeem code input, save, notify user, mark paid."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("redeem_pay_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    parts = admin_state.split("_")
    wid = int(parts[2])
    page = int(parts[3])

    context.user_data.pop("admin_state", None)
    code = update.message.text.strip()
    repository = Repository(await get_db())

    w = await repository.get_withdrawal(wid)
    if not w or w["status"] != "pending":
        await update.message.reply_text("❌ Withdrawal already processed.")
        return

    if code.lower() == "/cancel":
        await update.message.reply_text("❌ Canceled.")
        return

    # Save redeem code
    await repository.update_withdrawal_redeem_code(wid, code)

    # Mark as paid
    await repository.update_withdrawal_status(wid, "paid", user_id)

    # Notify user with their redeem code
    await notify_user(
        bot=context.bot,
        user_id=w["user_id"],
        text=(
            f"✅ <b>Withdrawal Successful!</b>\n\n"
            f"Your redeem code request <b>#{wid}</b> for "
            f"<b>{format_currency(w['amount'])}</b> has been approved.\n\n"
            f"🎫 <b>Your Redeem Code:</b>\n"
            f"<code>{escape_html(code)}</code>\n\n"
            f"Use this code to claim your funds. Thank you for using TASKHUB!"
        ),
    )

    await update.message.reply_text(
        f"✅ Redeem code sent to user #{w['user_id']} and request marked paid!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Redeem Queue", callback_data=f"admin:redeems_queue:{page}"),
             InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
        ])
    )


def register_handlers(application) -> None:
    """Register withdrawal admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_withdraws_menu_handler, pattern="^admin:withdraws_menu$"))
    application.add_handler(CallbackQueryHandler(admin_withdraws_queue_handler, pattern="^admin:withdraws_queue:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_wd_view_handler, pattern="^admin:wd_view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_wd_decision_handler, pattern="^admin:wd_decide:(approve|reject):\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_wd_custom_reason_start, pattern="^admin:wd_reason:\d+:\d+$"))

    # Redeem code admin handlers
    application.add_handler(CallbackQueryHandler(admin_redeems_queue_handler, pattern="^admin:redeems_queue:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_view_handler, pattern="^admin:redeem_view:\d+:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_redeem_pay_start_handler, pattern="^admin:redeem_pay:\d+:\d+$"))
    
    # Text input handlers for custom rejection reasons
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_withdrawals_text_handler
    ), group=7)

    # Text input handlers for redeem code payment
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_redeem_text_handler
    ), group=8)
