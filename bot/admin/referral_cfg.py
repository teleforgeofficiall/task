"""
referral_cfg.py — Admin interface to configure referral rewards.
Supports toggling between fixed, random range (lucky), and smart AI activity-weighted modes.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import referral_config_keyboard
from bot.utils import format_currency

logger = logging.getLogger(__name__)


async def admin_ref_config_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show referral rewards configuration panel."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    repository = Repository(await get_db())
    mode = await repository.get_setting("referral_mode", "random")
    fixed_reward = await repository.get_setting("fixed_referral_reward", 0.5)
    random_min = await repository.get_setting("random_reward_min", 0.5)
    random_max = await repository.get_setting("random_reward_max", 5.0)

    mode_description = ""
    if mode == "fixed":
        mode_description = f"🟢 Fixed reward mode is active: <b>{format_currency(fixed_reward)}</b> per referral invite."
    elif mode == "smart":
        mode_description = "🟢 Smart activity weighting mode is active: reward scale is computed dynamically (₹0.50 - ₹5.00) based on invitee tasks."
    else:
        mode_description = f"🟢 Random range mode is active: reward drops between <b>{format_currency(random_min)}</b> and <b>{format_currency(random_max)}</b> (Bot 2 table)."

    text = (
        f"🤝 <b>Referral Rewards Configurator</b>\n\n"
        f"{mode_description}\n\n"
        f"• Fixed Amount setting: <code>{format_currency(fixed_reward)}</code>\n"
        f"• Random Range setting: <code>{format_currency(random_min)} - {format_currency(random_max)}</code>\n\n"
        f"<i>Select a mode or configure its settings using the controls below.</i>"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=referral_config_keyboard(mode),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_ref_mode_toggle_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update active referral rewards mode (fixed/random/smart)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    mode = query.data.split(":")[2] # fixed / random / smart
    repository = Repository(await get_db())

    await repository.update_setting("referral_mode", mode)
    await query.answer(f"Switched to {mode.upper()} mode!")

    # Reload menu
    await admin_ref_config_menu_handler(update, context)


async def admin_ref_set_fixed_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for fixed reward amount value."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_ref_fixed_amt"

    text = (
        "🔧 <b>Set Fixed Referral Payout</b>\n\n"
        "Please send the reward amount in Rupees (e.g. <code>1.50</code>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:set_referral_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_ref_set_range_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for random range values."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_ref_range"

    text = (
        "🔧 <b>Set Random Range Limits</b>\n\n"
        "Please send the minimum and maximum reward limits separated by a vertical bar.\n"
        "Format: <code>min|max</code> (e.g. <code>0.50|3.00</code>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:set_referral_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_ref_config_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming config numeric inputs."""
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("awaiting_ref_"):
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()
    repository = Repository(await get_db())

    # Case A: Fixed Payout
    if admin_state == "awaiting_ref_fixed_amt":
        try:
            val = float(text.replace(",", ""))
            if val < 0:
                raise ValueError()
        except ValueError:
            await msg.reply_text("❌ Please send a valid positive number.")
            return

        context.user_data.pop("admin_state", None)
        await repository.update_setting("fixed_referral_reward", val)
        await repository.update_setting("referral_mode", "fixed")  # auto switch mode
        await msg.reply_text(
            f"✅ Fixed referral reward set to <b>{format_currency(val)}</b>! Mode auto-switched to <b>FIXED</b>.",
            parse_mode="HTML"
        )
        
    # Case B: Random Range
    elif admin_state == "awaiting_ref_range":
        parts = text.split("|")
        if len(parts) == 2:
            try:
                min_val = float(parts[0].strip())
                max_val = float(parts[1].strip())
                if min_val < 0 or max_val < min_val:
                    raise ValueError()
            except ValueError:
                await msg.reply_text("❌ Invalid bounds. Ensure positive numbers and max >= min.")
                return
        else:
            await msg.reply_text("❌ Invalid format. Please write as min|max (e.g. 0.50|5.00).")
            return

        context.user_data.pop("admin_state", None)
        await repository.update_setting("random_reward_min", min_val)
        await repository.update_setting("random_reward_max", max_val)
        await msg.reply_text(
            f"✅ Random reward range set to <b>{format_currency(min_val)} - {format_currency(max_val)}</b>!",
            parse_mode="HTML"
        )

    # Reload menu
    mode = await repository.get_setting("referral_mode", "random")
    await msg.reply_text(
        "🤝 Referral settings updated successfully.",
        reply_markup=referral_config_keyboard(mode)
    )


def register_handlers(application) -> None:
    """Register referral config handlers."""
    application.add_handler(CallbackQueryHandler(admin_ref_config_menu_handler, pattern="^admin:set_referral_config$"))
    application.add_handler(CallbackQueryHandler(admin_ref_mode_toggle_handler, pattern="^admin:ref_mode:(fixed|random|smart)$"))
    application.add_handler(CallbackQueryHandler(admin_ref_set_fixed_start, pattern="^admin:ref_set_fixed$"))
    application.add_handler(CallbackQueryHandler(admin_ref_set_range_start, pattern="^admin:ref_set_range$"))
    
    # Text input handlers for config values
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_ref_config_text_handler
    ), group=17)
