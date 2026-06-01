"""
referral.py — Referral dashboard, link generation, lucky reward claims, and invitee ranking lists.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import referral_keyboard
from bot.utils import edit_or_reply, format_currency

logger = logging.getLogger(__name__)


async def referral_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the referral dashboard with stats, links, and rewards."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    user_id = query.from_user.id
    bot_info = await context.bot.get_me()

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("❌ User profile not found.")
        return

    refer_paused = await repository.get_setting("refer_paused", False)
    banner_key = "img_refer_paused" if refer_paused else "img_refer_new"
    banner_url = await repository.get_image(banner_key)

    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    unclaimed_count = len(user.unclaimed_referrals)
    has_unclaimed = unclaimed_count > 0

    mode = await repository.get_setting("referral_mode", "random")
    reward_desc = ""
    if mode == "fixed":
        val = await repository.get_setting("fixed_referral_reward", 0.5)
        reward_desc = f"• Fixed: <b>{format_currency(val)}</b> per valid referral"
    elif mode == "smart":
        reward_desc = "• Smart: up to <b>₹5.00</b> based on invitee activity"
    else:
        reward_desc = "• Lucky Draw: <b>₹0.50 – ₹5.00</b> random reward per invitee"

    paused_notice = ""
    if refer_paused:
        paused_notice = "⚠️ <b>Referral program is paused.</b>\n\n"

    text = (
        f"🤝 <b>Refer & Earn</b>\n\n"
        f"{paused_notice}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<blockquote>Invite your friends to TaskHub and earn rewards when they join and complete tasks.</blockquote>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 <b>Your Referral Link</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"💡 <b>Reward Structure</b>\n"
        f"{reward_desc}\n\n"
        f"📊 <b>Your Statistics</b>\n"
        f"• 👥 <b>Total Invites:</b> <code>{len(user.referrals)}</code>\n"
        f"• ✅ <b>Rewarded:</b> <code>{len(user.rewarded_referrals) - unclaimed_count}</code>\n"
        f"• ⏳ <b>Pending:</b> <code>{unclaimed_count}</code>\n"
        f"• 💰 <b>Total Earned:</b> <code>{format_currency(user.referral_earnings)}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👇 Tap <b>Share Referral Link</b> to send this to your friends."
    )

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=referral_keyboard(has_unclaimed, ref_link),
        image_url=banner_url
    )


async def referral_claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Claim all unclaimed referral rewards in a batch."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    user_id = query.from_user.id

    user = await repository.get_user(user_id)
    if not user:
        await query.answer("❌ User profile not found.")
        return

    # Check inviter device verification (only if enabled)
    dev_verif_enabled = await repository.get_setting("device_verification_enabled", False)
    if dev_verif_enabled and not user.device_verified:
        await query.answer(
            "⚠️ Device verification required! Please verify your device in the Wallet section first.",
            show_alert=True
        )
        return

    unclaimed_list = list(user.unclaimed_referrals)
    if not unclaimed_list:
        await query.answer("❌ You don't have any unclaimed referral rewards.", show_alert=True)
        return

    # Claim rewards
    total_earned = 0.0
    claimed_count = 0

    for ref_id in unclaimed_list:
        # Atomic claim reward method returns reward amount or None
        amount = await repository.claim_referral_reward(user_id, ref_id)
        if amount is not None:
            total_earned += amount
            claimed_count += 1

    if claimed_count > 0:
        await query.answer(
            f"🎉 Claimed successfully!\nCredited {format_currency(total_earned)} for {claimed_count} referral(s).",
            show_alert=True
        )
    else:
        await query.answer("❌ No rewards were claimed.", show_alert=True)

    # Refresh page
    await referral_menu_handler(update, context)


async def referral_top_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View top referrals ranking leaderboard."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())

    all_users = await repository.get_all_users_cursor()
    sorted_users = sorted(all_users, key=lambda u: len(u.referrals), reverse=True)[:10]

    text_lines = []
    for rank, u in enumerate(sorted_users, 1):
        name = u.first_name
        uname = u.username or ""
        count = len(u.referrals)
        user_display = f"{name} (@{uname})" if uname else name
        text_lines.append(f"🏆 <b>#{rank}</b>. {user_display} — <code>{count}</code> invites")

    ranks_block = "\n".join(text_lines) if text_lines else "<i>No referral records found.</i>"
    
    text = (
        f"🏆 <b>Top Referral Rankings</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{ranks_block}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<i>Invite more friends to climb the leaderboard.</i>"
    )

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Refer Menu", callback_data="menu:refer")]
        ])
    )


def register_handlers(application) -> None:
    """Register referral handlers."""
    application.add_handler(CallbackQueryHandler(referral_menu_handler, pattern="^menu:refer$"))
    application.add_handler(CallbackQueryHandler(referral_claim_handler, pattern="^refer:claim$"))
    application.add_handler(CallbackQueryHandler(referral_top_handler, pattern="^refer:top$"))
