"""
users.py — Admin actions to search, audit, warn, ban, and adjust user balances.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import users_menu, user_action_keyboard, back_to_admin
from bot.utils import format_currency, escape_html

logger = logging.getLogger(__name__)


async def admin_users_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the users management menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    text = (
        "👥 <b>User Base Management</b>\n\n"
        "Search for users by Telegram ID or @username to modify their balances, "
        "warnings, bans, or audit their device fingerprints."
    )

    await query.edit_message_text(text=text, reply_markup=users_menu(), parse_mode="HTML")
    await query.answer()


async def admin_user_lookup_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Initiates user search mode."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_user_search"

    text = (
        "🔍 <b>User Lookup</b>\n\n"
        "Please send the user's <b>Telegram User ID</b> (e.g. <code>123456789</code>) "
        "or their <b>@username</b>."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:users_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def render_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Render full details and action control board for a specific user ID."""
    repository = Repository(await get_db())
    db_user = await repository.get_user(user_id)
    if not db_user:
        msg = f"❌ User ID <code>{user_id}</code> not found in database."
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg, parse_mode="HTML")
        return

    status = "🔴 BANNED" if db_user.banned else "🟢 Active"
    flagged = "🚩 Flagged (Suspicious)" if db_user.is_flagged else "🟢 Clear"
    wd_status = "🔒 Locked" if db_user.withdraw_locked else "🔓 Unlocked"
    device_status = "Verified" if db_user.device_verified else "Unverified"

    profile_text = (
        f"👤 <b>User Profile: {escape_html(db_user.first_name)}</b>\n"
        f"─────────────────────\n"
        f"• <b>ID:</b> <code>{db_user.user_id}</code>\n"
        f"• <b>Username:</b> @{escape_html(db_user.username) if db_user.username else 'None'}\n"
        f"• <b>Joined:</b> <code>{db_user.joined_at.split('T')[0]}</code>\n\n"
        f"💰 <b>Wallet Balance:</b>\n"
        f"• Current: <code>{format_currency(db_user.balance)}</code>\n"
        f"• Lifetime Earned: <code>{format_currency(db_user.lifetime_earnings)}</code>\n"
        f"• Referral Earnings: <code>{format_currency(db_user.referral_earnings)}</code>\n\n"
        f"🛡️ <b>Security & Standing:</b>\n"
        f"• Account Status: {status}\n"
        f"• Threat Flag: {flagged} (Reason: <i>{escape_html(db_user.flag_reason) if db_user.flag_reason else 'None'}</i>)\n"
        f"• Payout Gate: {wd_status}\n"
        f"• Warnings: <code>{db_user.warnings}/3</code>\n"
        f"• Fraud Score: <code>{db_user.fraud_score}</code>\n"
        f"• Device Verification: <code>{device_status}</code>\n\n"
        f"📊 <b>Activity Counts:</b>\n"
        f"• Tasks Completed: <code>{len(db_user.completed_tasks)}</code>\n"
        f"• Referrals Invited: <code>{len(db_user.referrals)}</code>\n"
        f"─────────────────────"
    )

    kb = user_action_keyboard(
        user_id=db_user.user_id,
        is_banned=db_user.banned,
        is_flagged=db_user.is_flagged,
        withdraw_locked=db_user.withdraw_locked
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(text=profile_text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text=profile_text, reply_markup=kb, parse_mode="HTML")


async def admin_users_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text inputs in admin search and balance adjustments."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()
    repository = Repository(await get_db())

    # Case A: User Search
    if admin_state == "awaiting_user_search":
        context.user_data.pop("admin_state", None)
        found_doc = await repository.search_user(text)
        if found_doc:
            await render_user_profile(update, context, found_doc["user_id"])
        else:
            await msg.reply_text(
                f"❌ No user matching <code>{escape_html(text)}</code> found.",
                parse_mode="HTML",
                reply_markup=users_menu()
            )
        return

    # Case B: Balance adjustment
    if admin_state.startswith("usr_bal_adj_"):
        target_uid = int(admin_state.replace("usr_bal_adj_", ""))
        context.user_data.pop("admin_state", None)

        try:
            amount = float(text)
        except ValueError:
            await msg.reply_text("❌ Invalid number. Adjustment aborted.")
            return

        new_bal = await repository.admin_adjust_balance(
            admin_id=user_id,
            user_id=target_uid,
            amount=amount,
            reason="Admin manual override adjustment"
        )

        await msg.reply_text(
            f"✅ Balance adjusted! New balance: <code>{format_currency(new_bal)}</code>",
            parse_mode="HTML"
        )
        await render_user_profile(update, context, target_uid)
        return


async def admin_user_toggle_lock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle withdrawal lock status."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    target_uid = int(query.data.split(":")[2])
    repository = Repository(await get_db())
    db_user = await repository.get_user(target_uid)
    if not db_user:
        return

    admin_id = query.from_user.id
    if db_user.withdraw_locked:
        await repository.unlock_withdrawal(target_uid, admin_id)
        await query.answer("Unlocked withdrawals.")
    else:
        await repository.lock_withdrawal(target_uid, admin_id)
        await query.answer("Locked withdrawals.")

    await render_user_profile(update, context, target_uid)


async def admin_user_warnings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add/Remove warnings for a user."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    action = query.data.split(":")[1] # usr_warn_add / usr_warn_rem
    target_uid = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    admin_id = query.from_user.id

    if "add" in action:
        cnt = await repository.add_warning(target_uid, admin_id)
        await query.answer(f"Warning added. Total: {cnt}/3")
    else:
        cnt = await repository.remove_warning(target_uid, admin_id)
        await query.answer(f"Warning removed. Total: {cnt}/3")

    await render_user_profile(update, context, target_uid)


async def admin_user_ban_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban/Unban user."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    target_uid = int(query.data.split(":")[2])
    repository = Repository(await get_db())
    db_user = await repository.get_user(target_uid)
    if not db_user:
        return

    admin_id = query.from_user.id

    if db_user.banned:
        await repository.unban_user(target_uid, admin_id)
        await query.answer("User unbanned.")
    else:
        await repository.ban_user(target_uid, admin_id, "Manual admin ban")
        await query.answer("User banned.")

    await render_user_profile(update, context, target_uid)


async def admin_user_flag_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Flag/Unflag user threat score."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    target_uid = int(query.data.split(":")[2])
    repository = Repository(await get_db())
    db_user = await repository.get_user(target_uid)
    if not db_user:
        return

    new_flag = not db_user.is_flagged
    reason = "Flagged by Admin" if new_flag else None
    await repository.update_user_fields(target_uid, is_flagged=new_flag, flag_reason=reason)
    await query.answer("Suspicious flag updated.")

    await render_user_profile(update, context, target_uid)


async def admin_user_bal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for balance edit amount."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    target_uid = int(query.data.split(":")[2])
    context.user_data["admin_state"] = f"usr_bal_adj_{target_uid}"
    context.user_data.pop("state", None)

    text = (
        "💵 <b>Adjust Wallet Balance</b>\n\n"
        "Send the adjustment value. Use positive numbers to credit, "
        "or negative numbers to debit (e.g. <code>+150.50</code> or <code>-75</code>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data=f"admin:usr_profile_{target_uid}")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_user_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback to render user profile directly."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    target_uid = int(query.data.replace("admin:usr_profile_", ""))
    await render_user_profile(update, context, target_uid)


async def admin_flagged_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render list of suspicious accounts (fraud_score > 50)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    page = int(query.data.split(":")[2])
    repository = Repository(await get_db())

    all_users = await repository.get_all_users_cursor()
    flagged_docs = [
        u for u in all_users
        if u.fraud_score > settings.FRAUD_SCORE_THRESHOLD
    ][:50]

    if not flagged_docs:
        await query.answer("No suspicious flagged accounts in system.", show_alert=True)
        return

    per_page = 5
    total_pages = (len(flagged_docs) + per_page - 1) // per_page
    
    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_docs = flagged_docs[start_idx:end_idx]

    keyboard = []
    for u in page_docs:
        name = u.first_name
        uid = u.user_id
        score = u.fraud_score
        keyboard.append([
            InlineKeyboardButton(f"🚩 {name} ({uid}) — Score: {score}", callback_data=f"admin:usr_profile_{uid}")
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:flagged_users:{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:flagged_users:{page+1}"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:users_menu")])

    text = (
        f"⚠️ <b>Suspicious Account Roster (Page {page+1}/{total_pages})</b>\n\n"
        f"Renders all accounts containing a threat score above "
        f"the threshold of <code>{settings.FRAUD_SCORE_THRESHOLD}</code>."
    )

    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


def register_handlers(application) -> None:
    """Register users admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_users_menu_handler, pattern="^admin:users_menu$"))
    application.add_handler(CallbackQueryHandler(admin_user_lookup_start_handler, pattern="^admin:user_lookup$"))
    application.add_handler(CallbackQueryHandler(admin_user_toggle_lock, pattern="^admin:usr_lock:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_user_warnings_handler, pattern="^admin:usr_warn_(add|rem):\d+$"))
    application.add_handler(CallbackQueryHandler(admin_user_ban_toggle, pattern="^admin:usr_ban:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_user_flag_toggle, pattern="^admin:usr_flag:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_user_bal_start, pattern="^admin:usr_bal:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_flagged_users_handler, pattern="^admin:flagged_users:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_user_profile_callback, pattern="^admin:usr_profile_\d+$"))
    
    # Text input handlers for user searching/adjusting balances
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_users_text_handler
    ), group=3)
