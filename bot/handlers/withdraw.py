"""
withdraw.py — Withdrawal request submissions, UPI format validation, and user withdrawal logs.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from datetime import datetime, timedelta, timezone
from bot.database import get_db, Repository
from bot.keyboards.user_kb import back_to_menu_keyboard
from bot.utils import edit_or_reply, format_currency, validate_upi_id
from bot.services.notifications import notify_admins

logger = logging.getLogger(__name__)


async def withdraw_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the withdrawal main dashboard with mode selection."""
    query = update.callback_query
    if not query:
        return

    # Reset any state
    context.user_data.pop("state", None)

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("❌ User profile not found.")
        return

    min_w = await repository.get_setting("min_withdraw", 10.0)
    max_w = await repository.get_setting("max_withdraw", 10000.0)
    daily_limit = await repository.get_setting("daily_withdraw_limit", 3)

    # Status notice
    status_notice = ""
    if user.withdraw_locked:
        status_notice = "🚫 <b>Your withdrawals are currently locked.</b> Please contact administration.\n\n"

    text = (
        f"💳 <b>Withdraw Wallet Funds</b>\n\n"
        f"{status_notice}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Your Balance:</b> <code>{format_currency(user.balance)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 <b>Withdrawal Limits</b>\n"
        f"• Minimum: <code>{format_currency(min_w)}</code> per transaction\n"
        f"• Maximum: <code>{format_currency(max_w)}</code> per transaction\n"
        f"• Daily Limit: <code>{daily_limit} withdrawal(s)</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Select your withdrawal method:</b>"
    )

    keyboard = []
    if not user.withdraw_locked and user.balance >= min_w:
        keyboard.append([InlineKeyboardButton("💳 UPI Transfer", callback_data="withdraw:request:upi")])
        keyboard.append([InlineKeyboardButton("🎫 Redeem Code", callback_data="withdraw:request:redeem")])
    
    keyboard.append([InlineKeyboardButton("📜 Withdrawal History", callback_data="withdraw:history")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")])

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def withdraw_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback to start withdrawal wizard — supports UPI and Redeem modes."""
    query = update.callback_query
    if not query:
        return

    parts = query.data.split(":")
    method = parts[2] if len(parts) > 2 else "upi"

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("❌ User profile not found.")
        return

    if user.withdraw_locked:
        await query.answer("🚫 Withdrawals are locked for this account.", show_alert=True)
        return

    daily_limit = await repository.get_setting("daily_withdraw_limit", 3)
    if daily_limit > 0:
        today_count = await repository.count_today_withdrawals(user_id)
        if today_count >= daily_limit:
            await query.answer(
                f"❌ Daily withdrawal limit reached ({daily_limit}/day). Please try again tomorrow.",
                show_alert=True
            )
            return

    min_w = await repository.get_setting("min_withdraw", 10.0)
    if user.balance < min_w:
        await query.answer(f"❌ Minimum withdrawal amount is {format_currency(min_w)}", show_alert=True)
        return

    # Check for pending withdrawals
    has_pending = await repository.has_pending_withdrawal(user_id)
    if has_pending:
        await query.answer("❌ You already have an active pending withdrawal request. Please wait.", show_alert=True)
        return

    if method == "redeem":
        # Redeem code flow: just ask for amount (no UPI needed)
        context.user_data["state"] = "withdraw_awaiting_redeem_amount"

        max_possible = min(user.balance, await repository.get_setting("max_withdraw", 10000.0))

        text = (
            "🎫 <b>Redeem Code Withdrawal</b>\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>Available Balance:</b> <code>{format_currency(user.balance)}</code>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Please send the <b>amount</b> you would like to withdraw as a redeem code.\n\n"
            f"<blockquote>Limits: <code>{format_currency(min_w)}</code> – <code>{format_currency(max_possible)}</code></blockquote>"
        )

        await edit_or_reply(
            update=update, context=context, text=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="menu:withdraw")]
            ])
        )
        return

    # UPI flow: ask for UPI ID first
    context.user_data["state"] = "withdraw_awaiting_upi"

    text = (
        "💳 <b>Withdrawal — Step 1 of 2</b>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>Please enter your <b>UPI ID</b> to receive your funds.\n"
        "Example: <code>username@bank</code> or <code>1234567890@paytm</code></blockquote>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<i>Type your UPI ID in this chat, or tap Cancel to go back.</i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="menu:withdraw")]
    ])

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=kb
    )


async def withdraw_text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes UPI ID, redeem amount, and withdrawal amount text inputs."""
    state = context.user_data.get("state", "")
    if not state.startswith("withdraw_"):
        return

    msg = update.message
    text = msg.text.strip()
    user_id = msg.from_user.id
    repository = Repository(await get_db())

    user = await repository.get_user(user_id)
    if not user:
        return

    # Cancel command helper
    if text.lower() == "/cancel":
        context.user_data.pop("state", None)
        await msg.reply_text("❌ Withdrawal process cancelled.")
        return

    # ── Redeem Code Amount Input ─────────────────────────────────────────────
    if state == "withdraw_awaiting_redeem_amount":
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await msg.reply_text("❌ Please enter a valid positive number.")
            return

        min_w = await repository.get_setting("min_withdraw", 10.0)
        max_w = await repository.get_setting("max_withdraw", 10000.0)

        if amount < min_w:
            await msg.reply_text(f"❌ Amount is below the minimum limit of {format_currency(min_w)}.")
            return
        if amount > max_w:
            await msg.reply_text(f"❌ Amount exceeds the maximum transaction limit of {format_currency(max_w)}.")
            return
        if amount > user.balance:
            await msg.reply_text(f"❌ Insufficient balance! Your current balance is {format_currency(user.balance)}.")
            return

        # Daily limit check
        daily_limit = await repository.get_setting("daily_withdraw_limit", 3)
        if daily_limit > 0:
            today_count = await repository.count_today_withdrawals(user_id)
            if today_count >= daily_limit:
                await msg.reply_text(f"❌ Daily withdrawal limit reached ({daily_limit}/day). Try again tomorrow.")
                context.user_data.pop("state", None)
                return

        # Pending check
        if await repository.has_pending_withdrawal(user_id):
            await msg.reply_text("❌ You already have an active pending withdrawal request.")
            context.user_data.pop("state", None)
            return

        # Deduct balance
        await repository.debit_balance(
            user_id=user_id, amount=amount,
            tx_type="withdrawal_pending",
            description=f"Redeem code withdrawal request of {format_currency(amount)}"
        )

        # Create redeem withdrawal request
        w_req = await repository.add_withdrawal(
            user_id, amount, method="redeem"
        )

        context.user_data.pop("state", None)

        # Success message with review timeline note
        await msg.reply_text(
            f"✅ <b>Withdrawal Submitted</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Request ID:</b> <code>#{w_req.id}</code>\n"
            f"• <b>Amount:</b> <code>{format_currency(amount)}</code>\n"
            f"• <b>Method:</b> Redeem Code 🎫\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<blockquote>⏰ Your request will be reviewed by an admin within 24–48 hours.\n"
            f"⚠️ Any suspicious activity may result in account suspension.</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Back to Wallet", callback_data="menu:wallet")]
            ])
        )

        # Admin alert for redeem
        await send_admin_withdrawal_alert(
            context.bot, repository, user, w_req.id, amount,
            method_label="Redeem Code 🎫", target_detail="(Redeem Code)"
        )
        return

    # ── Step 1: Receiving UPI ID ──────────────────────────────────────────────
    if state == "withdraw_awaiting_upi":
        if not validate_upi_id(text):
            await msg.reply_text(
                "❌ <b>Invalid UPI ID Format</b>\n\n"
                "Please verify and send a valid UPI ID.\n"
                "Example: <code>payee@ybl</code> or <code>9876543210@paytm</code>\n\n"
                "Send /cancel to abort.",
                parse_mode="HTML"
            )
            return

        # Save UPI and transition state
        context.user_data["state"] = f"withdraw_awaiting_amount_{text}"
        
        min_w = await repository.get_setting("min_withdraw", 10.0)
        max_w = await repository.get_setting("max_withdraw", 10000.0)
        max_possible = min(user.balance, max_w)

        await msg.reply_text(
            f"💳 <b>Withdrawal — Step 2 of 2</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<b>UPI Target:</b> <code>{text}</code>\n"
            f"<b>Available Balance:</b> <code>{format_currency(user.balance)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<blockquote>Please send the <b>amount</b> you wish to withdraw.\n"
            f"Limits: <code>{format_currency(min_w)}</code> – <code>{format_currency(max_possible)}</code></blockquote>\n\n"
            f"<i>Type the numeric amount in this chat.</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="menu:withdraw")]
            ])
        )
        return

    # ── Step 2: Receiving Amount (UPI mode) ───────────────────────────────────
    if state.startswith("withdraw_awaiting_amount_"):
        upi_id = state.replace("withdraw_awaiting_amount_", "")
        
        try:
            amount = float(text)
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await msg.reply_text("❌ Please enter a valid positive number.")
            return

        min_w = await repository.get_setting("min_withdraw", 10.0)
        max_w = await repository.get_setting("max_withdraw", 10000.0)

        if amount < min_w:
            await msg.reply_text(f"❌ Amount is below the minimum limit of {format_currency(min_w)}.")
            return
        if amount > max_w:
            await msg.reply_text(f"❌ Amount exceeds the maximum transaction limit of {format_currency(max_w)}.")
            return
        if amount > user.balance:
            await msg.reply_text(f"❌ Insufficient balance! Your current balance is {format_currency(user.balance)}.")
            return

        # Double check daily limit just before execution
        daily_limit = await repository.get_setting("daily_withdraw_limit", 3)
        if daily_limit > 0:
            today_count = await repository.count_today_withdrawals(user_id)
            if today_count >= daily_limit:
                await msg.reply_text(f"❌ Daily withdrawal limit reached ({daily_limit}/day). Try again tomorrow.")
                context.user_data.pop("state", None)
                return

        # Double check for pending request just before execution
        if await repository.has_pending_withdrawal(user_id):
            await msg.reply_text("❌ You already have an active pending withdrawal request.")
            context.user_data.pop("state", None)
            return

        # Deduct balance (debit ledger logs)
        await repository.debit_balance(
            user_id=user_id,
            amount=amount,
            tx_type="withdrawal_pending",
            description=f"Withdrawal request of {format_currency(amount)} to UPI {upi_id}"
        )

        # Create withdrawal request record
        w_req = await repository.add_withdrawal(user_id, amount, upi_id, method="upi")

        # Clear state
        context.user_data.pop("state", None)

        # Success message with review timeline note
        await msg.reply_text(
            f"✅ <b>Withdrawal Submitted</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Request ID:</b> <code>#{w_req.id}</code>\n"
            f"• <b>Amount:</b> <code>{format_currency(amount)}</code>\n"
            f"• <b>Target UPI ID:</b> <code>{upi_id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<blockquote>⏰ Your request will be reviewed by an admin within 24–48 hours.\n"
            f"⚠️ Any suspicious activity may result in account suspension.</blockquote>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Back to Wallet", callback_data="menu:wallet")]
            ])
        )

        # Admin alert with full user info + history button
        await send_admin_withdrawal_alert(
            context.bot, repository, user, w_req.id, amount,
            method_label="UPI 💳", target_detail=upi_id
        )


async def send_admin_withdrawal_alert(
    bot, repository, user, w_req_id: int, amount: float,
    method_label: str, target_detail: str,
) -> None:
    """Send enhanced withdrawal alert to admins with user stats + profile button."""
    user_id = user.user_id
    task_count = len(user.completed_tasks)
    ref_count = len(user.referrals)

    alert_text = (
        f"💸 <b>New Withdrawal Request (#{w_req_id})</b>\n\n"
        f"• <b>User:</b> {user.first_name} (ID: <code>{user_id}</code>)\n"
        f"• <b>Method:</b> {method_label}\n"
        f"• <b>Amount:</b> <b>{format_currency(amount)}</b>\n"
        f"• <b>Target:</b> <code>{target_detail}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>User Stats</b>\n"
        f"• Balance: <code>{format_currency(user.balance)}</code>\n"
        f"• Lifetime Earnings: <code>{format_currency(user.lifetime_earnings)}</code>\n"
        f"• Tasks Done: <code>{task_count}</code>\n"
        f"• Referrals: <code>{ref_count}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Audit and dispatch via admin panel.</i>"
    )

    from bot.keyboards.admin_kb import withdrawal_alert_keyboard
    await notify_admins(
        bot=bot,
        text=alert_text,
        reply_markup=withdrawal_alert_keyboard(user_id, w_req_id),
    )


async def withdrawal_history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback to view user withdrawal history."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    user_id = query.from_user.id

    history = await repository.get_user_withdrawal_history(user_id, limit=10)
    if not history:
        await edit_or_reply(
            update=update,
            context=context,
            text=(
                "📜 <b>Withdrawal History</b>\n\n"
                "<blockquote>You do not have any recorded withdrawal transactions yet.</blockquote>"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="menu:withdraw")]
            ])
        )
        return

    lines = []
    for w in history:
        status_emoji = "⏳" if w["status"] == "pending" else ("✅" if w["status"] == "paid" else "❌")
        date_str = w["date"].split("T")[0] if "T" in w["date"] else w["date"]
        lines.append(
            f"{status_emoji} <b>{date_str}</b> | <code>{format_currency(w['amount'])}</code> → <code>{w['upi_id']}</code>\n"
            f"└ Status: <b>{w['status'].upper()}</b>" + (f" (Reason: <i>{w['reject_reason']}</i>)" if w.get("reject_reason") else "")
        )

    text = (
        f"📜 <b>Withdrawal History (Last 10)</b>\n\n"
        + "\n\n".join(lines)
    )

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="menu:withdraw")]
        ])
    )


def register_handlers(application) -> None:
    """Register withdrawal handlers."""
    application.add_handler(CallbackQueryHandler(withdraw_menu_handler, pattern="^menu:withdraw$"))
    application.add_handler(CallbackQueryHandler(withdraw_request_handler, pattern="^withdraw:request:(upi|redeem)$"))
    application.add_handler(CallbackQueryHandler(withdrawal_history_handler, pattern="^withdraw:history$"))
    
    # Text handlers for inputting withdraw values
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        withdraw_text_input_handler
    ))
