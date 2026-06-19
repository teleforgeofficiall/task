"""
settings.py — Admin controls for general settings and message template customizations.
"""
from __future__ import annotations

import logging
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin, is_permanent_admin, PERMANENT_ADMIN_IDS
from bot.keyboards.admin_kb import settings_menu, messages_manager_keyboard, admin_ids_keyboard, back_to_admin
from bot.utils import escape_html

logger = logging.getLogger(__name__)


async def admin_settings_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings dashboard."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    repository = Repository(await get_db())
    refer_paused = await repository.get_setting("refer_paused", False)
    maintenance_on = await repository.get_setting("maintenance_mode", False)
    min_w = await repository.get_setting("min_withdraw", 10.0)
    max_w = await repository.get_setting("max_withdraw", 10000.0)
    bonus_val = await repository.get_setting("daily_bonus", 0.5)

    text = (
        f"⚙️ <b>TASKHUB Global Parameters</b>\n\n"
        f"💳 <b>Withdrawals:</b>\n"
        f"• Min limit: <code>₹{min_w:.2f}</code>\n"
        f"• Max limit: <code>₹{max_w:.2f}</code>\n\n"
        f"🎁 <b>Daily Reward:</b>\n"
        f"• Bonus credit: <code>₹{bonus_val:.2f}</code>\n\n"
        f"<i>Configure rules, forced subscribe flows, ads, banners, "
        f"and default UI messages below.</i>"
    )

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=settings_menu(refer_paused=refer_paused, maintenance_on=maintenance_on),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "message is not modified" not in str(e).lower():
            raise
    await query.answer()


async def admin_settings_toggle_refer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle referral claim lock status."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("refer_paused", False)
    new_val = not current
    await repository.update_setting("refer_paused", new_val)
    
    status = "PAUSED" if new_val else "ACTIVE"
    await query.answer(f"Referral program is now {status}!")

    # Refresh
    await admin_settings_menu_handler(update, context)


async def admin_settings_toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle maintenance mode ON/OFF."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    repository = Repository(await get_db())
    current = await repository.get_setting("maintenance_mode", False)
    new_val = not current
    await repository.update_setting("maintenance_mode", new_val)

    status = "ON" if new_val else "OFF"
    await query.answer(f"Maintenance mode is now {status}!")

    await admin_settings_menu_handler(update, context)


async def admin_manage_admins_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current admin IDs as inline buttons with add/remove options."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    repository = Repository(await get_db())
    admin_ids = await repository.get_setting("admin_ids", [])
    users = await repository.get_users_by_ids(admin_ids)
    user_names = {u.id: u.first_name or f"User {u.id}" for u in users}
    for aid in admin_ids:
        if aid not in user_names:
            user_names[aid] = f"User {aid}"

    permanent_text = ""
    for pid in PERMANENT_ADMIN_IDS:
        name = user_names.get(pid, f"User {pid}")
        permanent_text += f"🔒 <b>{name}</b> (<code>{pid}</code>) — <i>permanent</i>\n"

    text = (
        "👑 <b>Admin Management</b>\n\n"
        f"{permanent_text}\n"
        "• 🔒 = Permanent (cannot be removed)\n"
        "• 👤 = Removable (tap to remove)\n\n"
        "Tap ➕ <b>Add New Admin</b> to add a Telegram user ID."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=admin_ids_keyboard(admin_ids, PERMANENT_ADMIN_IDS, user_names),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin to enter a new admin ID to add."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data["admin_state"] = "awaiting_new_admin_id"
    text = (
        "👑 <b>Add New Admin</b>\n\n"
        "Send the Telegram <b>User ID</b> of the person you want to add as admin.\n\n"
        "Type /cancel to abort."
    )
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:manage_admins")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_remove_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove an admin by ID (permanent admins cannot be removed)."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    parts = query.data.split(":")
    if len(parts) < 3:
        await query.answer("Invalid data")
        return

    try:
        remove_id = int(parts[2])
    except ValueError:
        await query.answer("Invalid ID")
        return

    if is_permanent_admin(remove_id):
        await query.answer("❌ This admin is permanent and cannot be removed!", show_alert=True)
        return

    if remove_id == query.from_user.id:
        await query.answer("❌ You cannot remove yourself!", show_alert=True)
        return

    repository = Repository(await get_db())
    admin_ids = await repository.get_setting("admin_ids", [])
    if remove_id not in admin_ids:
        await query.answer("This user is not an admin.")
        return

    admin_ids = [a for a in admin_ids if a != remove_id]
    await repository.update_setting("admin_ids", admin_ids)
    from bot.admin.panel import refresh_admin_ids
    await refresh_admin_ids()

    await query.answer(f"✅ Removed admin {remove_id}")

    # Refresh the admin list view
    await admin_manage_admins_start(update, context)


async def admin_messages_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show customized messages menu."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    text = (
        "📝 <b>Custom Message Editor</b>\n\n"
        "Customize template copy and notifications sent by the bot. "
        "Support standard HTML styling tags (e.g. <code>&lt;b&gt;</code>, "
        "<code>&lt;code&gt;</code>, <code>&lt;blockquote&gt;</code>)."
    )

    await query.edit_message_text(
        text=text,
        reply_markup=messages_manager_keyboard(),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_msg_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for message content edits."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    key = query.data.split(":")[2] # start_message / launch_message / ban_message
    context.user_data["admin_state"] = f"edit_msg_{key}"

    repository = Repository(await get_db())
    current_val = await repository.get_setting(key, "")

    text = (
        f"📝 <b>Edit Template: {key.replace('_', ' ').upper()}</b>\n\n"
        f"Current text:\n"
        f"─────────────────────\n"
        f"{current_val}\n"
        f"─────────────────────\n\n"
        f"Please send the new formatted HTML text template.\n"
        f"<i>Type /cancel to abort.</i>"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:set_messages")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


async def admin_settings_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process incoming text template updates and admin ID changes."""
    if context.user_data is None:
        return
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state:
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()
    repository = Repository(await get_db())

    if text.lower() == "/cancel":
        context.user_data.pop("admin_state", None)
        await msg.reply_text("❌ Cancelled.", reply_markup=messages_manager_keyboard())
        return

    if admin_state == "awaiting_new_admin_id":
        try:
            new_id = int(text.strip())
        except ValueError:
            await msg.reply_text("❌ Invalid ID. Please send a numeric User ID.")
            return

        if new_id <= 0:
            await msg.reply_text("❌ Invalid ID. User IDs are positive numbers.")
            return

        admin_ids = await repository.get_setting("admin_ids", [])
        if new_id in admin_ids:
            await msg.reply_text(f"❌ User <code>{new_id}</code> is already an admin.", parse_mode="HTML")
            return

        if new_id in PERMANENT_ADMIN_IDS:
            await msg.reply_text(f"✅ User <code>{new_id}</code> is already a permanent admin.", parse_mode="HTML")
            context.user_data.pop("admin_state", None)
            return

        admin_ids.append(new_id)
        await repository.update_setting("admin_ids", admin_ids)
        from bot.admin.panel import refresh_admin_ids
        await refresh_admin_ids()
        context.user_data.pop("admin_state", None)

        users = await repository.get_users_by_ids([new_id])
        name = users[0].first_name if users else str(new_id)

        await msg.reply_text(
            f"✅ <b>{name}</b> (<code>{new_id}</code>) added as admin!",
            parse_mode="HTML",
            reply_markup=back_to_admin()
        )
        return

    # ─── Ad Goal Config ───────────────────────────────────────────────
    if admin_state == "set_ad_goal":
        parts = text.split("|")
        if len(parts) != 2:
            await msg.reply_text("❌ Invalid format. Use: <code>target|reward</code> (e.g. 20|1.5).", parse_mode="HTML")
            return
        try:
            target = int(parts[0].strip())
            reward = float(parts[1].strip())
            if target <= 0 or reward <= 0:
                raise ValueError
        except ValueError:
            await msg.reply_text("❌ Invalid numbers. Target must be a whole number > 0, reward must be > 0.")
            return
        context.user_data.pop("admin_state", None)
        await repository.update_setting("ad_goal_target", target)
        await repository.update_setting("ad_goal_reward", reward)
        await msg.reply_text(f"✅ Ad goal set: {target} ads, \u20b9{reward:.2f} reward.", reply_markup=back_to_admin())
        return

    # ─── Promo Config ─────────────────────────────────────────────────
    if admin_state == "promo_set_price":
        try:
            val = float(text.replace(",", ""))
            if val <= 0:
                raise ValueError
        except ValueError:
            await msg.reply_text("❌ Invalid price. Send a positive number.")
            return
        context.user_data.pop("admin_state", None)
        await repository.update_setting("promo_price", val)
        await msg.reply_text(f"✅ Promo price set to \u20b9{val:.2f}.", reply_markup=back_to_admin())
        return

    if admin_state == "promo_set_qr":
        context.user_data.pop("admin_state", None)
        if text.strip().lower() == "clear":
            await repository.update_setting("promo_qr_image", "")
            await msg.reply_text("✅ Promo QR code cleared.", reply_markup=back_to_admin())
        else:
            await repository.update_setting("promo_qr_image", text.strip())
            await msg.reply_text("✅ Promo QR image URL updated.", reply_markup=back_to_admin())
        return

    # ─── Miniapp URL ───────────────────────────────────────────────────
    if admin_state == "set_miniapp_url":
        url = text.strip().rstrip("/")
        context.user_data.pop("admin_state", None)
        await repository.update_setting("miniapp_url", url)
        await msg.reply_text(f"✅ MiniApp URL set to:\n<code>{url}</code>", parse_mode="HTML", reply_markup=back_to_admin())
        return

    if not admin_state.startswith("edit_msg_"):
        return

    key = admin_state.replace("edit_msg_", "")
    context.user_data.pop("admin_state", None)

    # Update template in DB
    await repository.update_setting(key, text)

    await msg.reply_text(
        f"✅ Template <b>{key.upper()}</b> successfully updated!",
        parse_mode="HTML",
        reply_markup=messages_manager_keyboard()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AD GOAL CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_set_ad_goal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for ad goal target and reward."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "set_ad_goal"
    repo = Repository(await get_db())
    target = await repo.get_setting("ad_goal_target", 20)
    reward = await repo.get_setting("ad_goal_reward", 1.0)
    await query.edit_message_text(
        "📊 <b>Ad Goal Configuration</b>\n\n"
        f"Current Target: <code>{target}</code> ads\n"
        f"Current Reward: <code>\u20b9{reward:.2f}</code>\n\n"
        "Send the new target and reward separated by a vertical bar.\n"
        "Format: <code>target|reward</code> (e.g. <code>20|1.5</code>).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:settings_menu")]
        ])
    )
    await query.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# PROMO CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_set_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show promo config options."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    repo = Repository(await get_db())
    price = await repo.get_setting("promo_price", 50.0)
    qr = await repo.get_setting("promo_qr_image", "")
    text = (
        "🏷️ <b>Promo Configuration</b>\n\n"
        f"💰 Price: <code>\u20b9{price:.2f}</code>\n"
        f"📱 QR Code: {'<i>Not set</i>' if not qr else f'<code>{qr}</code>'}\n\n"
        "Choose what to update:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Set Promo Price", callback_data="admin:promo_set_price")],
        [InlineKeyboardButton("📱 Set Promo QR URL", callback_data="admin:promo_set_qr")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ])
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=kb)
    await query.answer()


async def admin_promo_set_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "promo_set_price"
    await query.edit_message_text(
        "💰 <b>Set Promo Price</b>\n\n"
        "Send the promo price in Rupees (e.g. <code>50</code>).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:set_promo")]
        ])
    )
    await query.answer()


async def admin_promo_set_qr_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "promo_set_qr"
    await query.edit_message_text(
        "📱 <b>Set Promo QR Image URL</b>\n\n"
        "Send the direct image URL for the promo QR code.\n"
        "Send <code>clear</code> to remove the current QR.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:set_promo")]
        ])
    )
    await query.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# MINIAPP URL
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_set_miniapp_url_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt admin for MiniApp URL."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data["admin_state"] = "set_miniapp_url"
    repo = Repository(await get_db())
    current = await repo.get_setting("miniapp_url", "https://taskhub-khaki.vercel.app")
    await query.edit_message_text(
        "🌐 <b>Set MiniApp URL</b>\n\n"
        f"Current: <code>{current}</code>\n\n"
        "Send the new Mini App URL.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="admin:settings_menu")]
        ])
    )
    await query.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# RESET DATA
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_reset_data_cli(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show CLI-based reset instructions."""
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    await query.edit_message_text(
        text=(
            "⚠️ <b>Reset All Data</b>\n\n"
            "Reset cannot be done from Telegram. "
            "Run this command in your VPS terminal:\n\n"
            "<code>cd /opt/taskhub && systemctl stop taskhub</code>\n"
            "<code>venv/bin/python scripts/reset_database.py</code>\n"
            "<code>systemctl start taskhub</code>\n\n"
            "This will <b>permanently delete ALL</b> data."
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


def register_handlers(application) -> None:
    """Register settings admin handlers."""
    application.add_handler(CallbackQueryHandler(admin_settings_menu_handler, pattern="^admin:settings_menu$"))
    application.add_handler(CallbackQueryHandler(admin_settings_toggle_refer, pattern="^admin:set_toggle_refer$"))
    application.add_handler(CallbackQueryHandler(admin_settings_toggle_maintenance, pattern="^admin:set_toggle_maintenance$"))
    application.add_handler(CallbackQueryHandler(admin_manage_admins_start, pattern="^admin:manage_admins$"))
    application.add_handler(CallbackQueryHandler(admin_add_admin_start, pattern="^admin:add_admin_start$"))
    application.add_handler(CallbackQueryHandler(admin_remove_admin_callback, pattern="^admin:remove_admin:\\d+$"))
    application.add_handler(CallbackQueryHandler(admin_messages_menu_handler, pattern="^admin:set_messages$"))
    application.add_handler(CallbackQueryHandler(admin_msg_edit_start, pattern="^admin:msg_edit:[a-z_]+$"))
    application.add_handler(CallbackQueryHandler(admin_set_ad_goal_start, pattern="^admin:set_ad_goal$"))
    application.add_handler(CallbackQueryHandler(admin_set_promo_start, pattern="^admin:set_promo$"))
    application.add_handler(CallbackQueryHandler(admin_promo_set_price_start, pattern="^admin:promo_set_price$"))
    application.add_handler(CallbackQueryHandler(admin_promo_set_qr_start, pattern="^admin:promo_set_qr$"))
    application.add_handler(CallbackQueryHandler(admin_set_miniapp_url_start, pattern="^admin:set_miniapp_url$"))
    application.add_handler(CallbackQueryHandler(admin_reset_data_cli, pattern="^admin:reset_data_cli$"))

    # Text input handlers for updating templates
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_settings_text_handler
    ), group=2)
