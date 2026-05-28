from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import withdraw_config_keyboard, star_config_keyboard
from bot.utils import format_currency

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


async def admin_withdraw_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())

    min_w = await repository.get_setting("min_withdraw", 10.0)
    max_w = await repository.get_setting("max_withdraw", 10000.0)
    daily_limit = await repository.get_setting("daily_withdraw_limit", 3)
    star_rate = await repository.get_setting("star_rate", 2.0)
    star_enabled = await repository.get_setting("star_withdraw_enabled", True)

    text = (
        "💰 <b>Withdrawal Configuration</b>\n\n"
        f"• <b>Minimum per withdrawal:</b> <code>{format_currency(min_w)}</code>\n"
        f"• <b>Maximum per withdrawal:</b> <code>{format_currency(max_w)}</code>\n"
        f"• <b>Daily withdrawal limit:</b> <code>{daily_limit} times</code>\n"
        f"• <b>Star Rate:</b> <code>1⭐ = ₹{star_rate:.0f}</code>\n"
        f"• <b>Star Withdraw:</b> <code>{'Enabled ✅' if star_enabled else 'Disabled ❌'}</code>\n\n"
        "Select an option below to change a value."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=withdraw_config_keyboard(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_wc_set_min_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "wc_set_min"

    repository = Repository(await get_db())
    current = await repository.get_setting("min_withdraw", 10.0)

    await query.edit_message_text(
        text=(
            f"💰 <b>Set Minimum Withdrawal Amount</b>\n\n"
            f"Current minimum: <code>{format_currency(current)}</code>\n\n"
            "Send the new minimum amount (e.g. <code>20</code>)."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:withdraw_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_wc_set_max_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "wc_set_max"

    repository = Repository(await get_db())
    current = await repository.get_setting("max_withdraw", 10000.0)

    await query.edit_message_text(
        text=(
            f"💰 <b>Set Maximum Withdrawal Amount</b>\n\n"
            f"Current maximum: <code>{format_currency(current)}</code>\n\n"
            "Send the new maximum amount (e.g. <code>5000</code>)."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:withdraw_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_wc_set_daily_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "wc_set_daily"

    repository = Repository(await get_db())
    current = await repository.get_setting("daily_withdraw_limit", 3)

    await query.edit_message_text(
        text=(
            f"📅 <b>Set Daily Withdrawal Limit</b>\n\n"
            f"Current limit: <code>{current} times per day</code>\n\n"
            "Send the new daily limit (e.g. <code>5</code>). Set <code>0</code> for unlimited."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:withdraw_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_wc_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        admin_state = context.user_data.get("admin_state", "")
        if not admin_state.startswith("wc_set_"):
            return

        user_id = update.effective_user.id
        if not is_admin(user_id):
            return

        msg = update.message
        text = msg.text.strip()
        logger.info("Admin %s setting wc_config: %s (state=%s)", user_id, text, admin_state)
        repository = Repository(await get_db())

        if text.lower() == "/cancel":
            context.user_data.pop("admin_state", None)
            await admin_withdraw_config_redirect(msg, context, repository)
            return

        try:
            if admin_state == "wc_set_min":
                value = round(float(text), 2)
                if value <= 0:
                    raise ValueError
                await repository.update_setting("min_withdraw", value)
                await msg.reply_text(f"✅ Minimum withdrawal set to <code>{format_currency(value)}</code>.", parse_mode="HTML")

            elif admin_state == "wc_set_max":
                value = round(float(text), 2)
                if value <= 0:
                    raise ValueError
                await repository.update_setting("max_withdraw", value)
                await msg.reply_text(f"✅ Maximum withdrawal set to <code>{format_currency(value)}</code>.", parse_mode="HTML")

            elif admin_state == "wc_set_daily":
                value = int(text)
                if value < 0:
                    raise ValueError
                await repository.update_setting("daily_withdraw_limit", value)
                limit_text = "unlimited" if value == 0 else f"{value} times per day"
                await msg.reply_text(f"✅ Daily withdrawal limit set to <code>{limit_text}</code>.", parse_mode="HTML")

            elif admin_state == "sc_set_rate":
                value = round(float(text), 2)
                if value <= 0:
                    raise ValueError
                await repository.update_setting("star_rate", value)
                await msg.reply_text(f"✅ Star rate set to <code>1⭐ = ₹{value:.0f}</code>.", parse_mode="HTML")

            elif admin_state == "sc_set_min_stars":
                value = int(text)
                if value < 0:
                    raise ValueError
                await repository.update_setting("min_star_withdraw", value)
                await msg.reply_text(f"✅ Minimum stars set to <code>{value}⭐</code>.", parse_mode="HTML")

            elif admin_state == "sc_set_max_stars":
                value = int(text)
                if value <= 0:
                    raise ValueError
                await repository.update_setting("max_star_withdraw", value)
                await msg.reply_text(f"✅ Maximum stars set to <code>{value}⭐</code>.", parse_mode="HTML")

            else:
                return

        except (ValueError, TypeError):
            await msg.reply_text("❌ Invalid value. Please send a valid positive number.")
            return

        context.user_data.pop("admin_state", None)
        await admin_withdraw_config_redirect(msg, context, repository)
    except Exception as e:
        logger.exception("Error in admin_wc_text_handler: %s", e)
        try:
            await update.message.reply_text("❌ An unexpected error occurred. Please try again.")
        except Exception:
            pass


async def admin_withdraw_config_redirect(msg, context, repository: Repository) -> None:
    min_w = await repository.get_setting("min_withdraw", 10.0)
    max_w = await repository.get_setting("max_withdraw", 10000.0)
    daily_limit = await repository.get_setting("daily_withdraw_limit", 3)
    star_rate = await repository.get_setting("star_rate", 2.0)
    star_enabled = await repository.get_setting("star_withdraw_enabled", True)

    text = (
        "💰 <b>Withdrawal Configuration</b>\n\n"
        f"• <b>Minimum per withdrawal:</b> <code>{format_currency(min_w)}</code>\n"
        f"• <b>Maximum per withdrawal:</b> <code>{format_currency(max_w)}</code>\n"
        f"• <b>Daily withdrawal limit:</b> <code>{daily_limit} times</code>\n"
        f"• <b>Star Rate:</b> <code>1⭐ = ₹{star_rate:.0f}</code>\n"
        f"• <b>Star Withdraw:</b> <code>{'Enabled ✅' if star_enabled else 'Disabled ❌'}</code>\n\n"
        "Select an option below to change a value."
    )

    await context.bot.send_message(
        chat_id=msg.chat_id,
        text=text,
        reply_markup=withdraw_config_keyboard(),
        parse_mode="HTML"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STAR CONFIG HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_star_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())

    star_rate = await repository.get_setting("star_rate", 2.0)
    star_enabled = await repository.get_setting("star_withdraw_enabled", True)
    min_stars = await repository.get_setting("min_star_withdraw", 1)
    max_stars = await repository.get_setting("max_star_withdraw", 500)

    text = (
        "⭐ <b>Star Withdraw Configuration</b>\n\n"
        f"• <b>Star Rate:</b> <code>1⭐ = ₹{star_rate:.0f}</code>\n"
        f"• <b>Status:</b> <code>{'Enabled ✅' if star_enabled else 'Disabled ❌'}</code>\n"
        f"• <b>Min Stars:</b> <code>{min_stars}⭐</code>\n"
        f"• <b>Max Stars:</b> <code>{max_stars}⭐</code>\n\n"
        "Select an option below to change a value."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=star_config_keyboard(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_sc_set_rate_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "sc_set_rate"

    repository = Repository(await get_db())
    current = await repository.get_setting("star_rate", 2.0)

    await query.edit_message_text(
        text=(
            f"⭐ <b>Set Star Rate</b>\n\n"
            f"Current: <code>1⭐ = ₹{current:.0f}</code>\n\n"
            "Send the new rate (e.g. <code>2</code> for ₹2 per star)."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:star_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_sc_set_min_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "sc_set_min_stars"

    repository = Repository(await get_db())
    current = await repository.get_setting("min_star_withdraw", 1)

    await query.edit_message_text(
        text=(
            f"⭐ <b>Set Minimum Stars</b>\n\n"
            f"Current: <code>{current}⭐</code>\n\n"
            "Send the new minimum star amount (e.g. <code>1</code>)."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:star_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_sc_set_max_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "sc_set_max_stars"

    repository = Repository(await get_db())
    current = await repository.get_setting("max_star_withdraw", 500)

    await query.edit_message_text(
        text=(
            f"⭐ <b>Set Maximum Stars</b>\n\n"
            f"Current: <code>{current}⭐</code>\n\n"
            "Send the new maximum star amount (e.g. <code>500</code>)."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:star_config")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_sc_toggle_enable_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("star_withdraw_enabled", True)
    new_val = not current
    await repository.update_setting("star_withdraw_enabled", new_val)

    await query.answer(f"Star withdraw {'enabled' if new_val else 'disabled'}!")
    # Refresh the config menu
    await admin_star_config_handler(update, context)


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(admin_withdraw_config_handler, pattern="^admin:withdraw_config$"))
    application.add_handler(CallbackQueryHandler(admin_wc_set_min_start, pattern="^admin:wc_set_min$"))
    application.add_handler(CallbackQueryHandler(admin_wc_set_max_start, pattern="^admin:wc_set_max$"))
    application.add_handler(CallbackQueryHandler(admin_wc_set_daily_start, pattern="^admin:wc_set_daily$"))

    # Star config handlers
    application.add_handler(CallbackQueryHandler(admin_star_config_handler, pattern="^admin:star_config$"))
    application.add_handler(CallbackQueryHandler(admin_sc_set_rate_start, pattern="^admin:sc_set_rate$"))
    application.add_handler(CallbackQueryHandler(admin_sc_set_min_stars_start, pattern="^admin:sc_set_min_stars$"))
    application.add_handler(CallbackQueryHandler(admin_sc_set_max_stars_start, pattern="^admin:sc_set_max_stars$"))
    application.add_handler(CallbackQueryHandler(admin_sc_toggle_enable_handler, pattern="^admin:sc_toggle_enable$"))

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_wc_text_handler
    ), group=6)
