from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
from telegram.error import RetryAfter, Forbidden, BadRequest, TelegramError

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.keyboards.admin_kb import broadcast_menu, back_to_admin
from bot.services.broadcaster import Broadcaster
from bot.utils import get_ist_now, format_currency, escape_html

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


# ─── Admin Broadcast Menu ─────────────────────────────────────────────────────

async def admin_broadcast_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    context.user_data.pop("admin_state", None)

    text = (
        "📢 <b>Global Announcement Broadcast</b>\n\n"
        "Draft and send messages (supports formatting, photos, links, and inline buttons) "
        "to targeted user segments."
    )

    await query.edit_message_text(text=text, reply_markup=broadcast_menu(), parse_mode="HTML")
    await query.answer()


async def admin_broadcast_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    target = query.data.split(":")[2]

    if target == "drop_rain":
        context.user_data["admin_state"] = "awaiting_drop_rain_config"
        text = (
            "💰 <b>Bonus Drop Setup</b>\n\n"
            "Send the <b>amount</b> and <b>max users</b> in this format:\n\n"
            "<code>amount,max_users</code>\n\n"
            "Example: <code>10,500</code> (₹10 each for max 500 users)\n\n"
            "<i>First-come-first-serve basis. Users who claim first get the bonus.</i>"
        )
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancel", callback_data="admin:broadcast_menu")]
            ]),
            parse_mode="HTML"
        )
        await query.answer()
        return

    context.user_data["bc_target"] = target
    context.user_data["admin_state"] = "awaiting_bc_message"

    text = (
        f"📢 <b>Broadcast to segment: {target.upper()}</b>\n\n"
        f"Please send the message you wish to broadcast.\n\n"
        f"• You can send <b>formatted text</b>, or a <b>photo with a caption</b>.\n"
        f"• You can also <b>FORWARD</b> any message from another channel/chat, and the bot will copy it exactly.\n\n"
        f"<i>Type /cancel to abort.</i>"
    )

    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Cancel", callback_data="admin:broadcast_menu")]
        ]),
        parse_mode="HTML"
    )
    await query.answer()


# ─── Drop Rain Config Handler ──────────────────────────────────────────────────

async def admin_drop_rain_config_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data is None:
        return
    admin_state = context.user_data.get("admin_state", "")
    if admin_state != "awaiting_drop_rain_config":
        return

    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    msg = update.message
    text = msg.text.strip()

    if text.lower() == "/cancel":
        context.user_data.pop("admin_state", None)
        await msg.reply_text("❌ Bonus Drop cancelled.", reply_markup=back_to_admin())
        return

    try:
        parts = text.split(",")
        if len(parts) != 2:
            raise ValueError
        amount = round(float(parts[0].strip()), 2)
        max_users = int(parts[1].strip())
        if amount <= 0 or max_users <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await msg.reply_text(
            "❌ Invalid format! Please send like: <code>10,500</code> (amount,max_users)",
            parse_mode="HTML"
        )
        return

    context.user_data.pop("admin_state", None)
    repository = Repository(await get_db())

    drop_id = str(uuid.uuid4())[:8]
    drop_state = {
        "id": drop_id,
        "amount": amount,
        "max_claims": max_users,
        "claimed_user_ids": [],
        "active": True,
    }
    await repository.set_drop_rain_state(drop_state)

    # Get all user IDs
    all_users = await repository.get_all_user_ids()
    if not all_users:
        await msg.reply_text("❌ No users in the database.", reply_markup=back_to_admin())
        return

    # Send progress message
    prog_msg = await msg.reply_text(
        f"💰 <b>Bonus Drop Started!</b>\n\n"
        f"Targeting <code>{len(all_users)}</code> users (max <code>{max_users}</code> claims)",
        parse_mode="HTML"
    )

    # Get the drop image
    img_url = await repository.get_image("img_drop_rain")

    drop_text = (
        "💸 <b>BONUS DROP!</b>\n\n"
        "🎉 <b>TASKHUB TEAM</b> has released a special bonus drop for users.\n\n"
        f"💰 <b>Reward:</b> <code>₹{amount:.2f}</code>\n"
        f"👥 Limited claims available for the first <b>{max_users}</b> users only.\n\n"
        "⚡ <i>First come, first served.</i>\n"
        "Tap the button below and claim your bonus before it ends!"
    )

    claim_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💸 Claim ₹{amount:.2f} Bonus", callback_data=f"drop_rain:claim:{drop_id}")]
    ])

    await repository.log_admin_action(
        admin_id=user_id,
        action="bonus_drop_start",
        target="all_users",
        details={"amount": amount, "max_users": max_users, "drop_id": drop_id}
    )

    # Fire-and-forget broadcast with fresh session
    repo_session = await get_db()
    fresh_repo = Repository(repo_session)
    asyncio.create_task(
        run_bonus_drop_broadcast(
            bot=context.bot,
            repository=fresh_repo,
            admin_chat_id=user_id,
            progress_message_id=prog_msg.message_id,
            user_ids=all_users,
            image_url=img_url,
            caption=drop_text,
            reply_markup=claim_kb,
            drop_id=drop_id,
        )
    )


async def run_bonus_drop_broadcast(
    bot, repository, admin_chat_id, progress_message_id,
    user_ids, image_url, caption, reply_markup, drop_id,
) -> None:
    total = len(user_ids)
    sent = 0
    blocked = 0
    failed = 0

    try:
        for idx, uid in enumerate(user_ids):
            try:
                if image_url:
                    await bot.send_photo(
                        chat_id=uid,
                        photo=image_url,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                else:
                    await bot.send_message(
                        chat_id=uid,
                        text=caption,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                sent += 1
            except (Forbidden, BadRequest):
                # Fallback: try plain text if photo fails
                if image_url:
                    try:
                        await bot.send_message(chat_id=uid, text=caption, reply_markup=reply_markup, parse_mode="HTML")
                        sent += 1
                        continue
                    except Exception:
                        pass
                blocked += 1
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try:
                    if image_url:
                        await bot.send_photo(chat_id=uid, photo=image_url, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
                    else:
                        await bot.send_message(chat_id=uid, text=caption, reply_markup=reply_markup, parse_mode="HTML")
                    sent += 1
                except Exception:
                    blocked += 1
            except Exception:
                failed += 1

            if (idx + 1) % 25 == 0 or idx == total - 1:
                try:
                    pct = ((idx + 1) / total) * 100
                    await bot.edit_message_text(
                        chat_id=admin_chat_id,
                        message_id=progress_message_id,
                        text=(
                            f"💰 <b>Bonus Drop Progress ({pct:.1f}%)</b>\n\n"
                            f"Total: <code>{total}</code>\n"
                            f"✅ Sent: <code>{sent}</code>\n"
                            f"🚫 Blocked: <code>{blocked}</code>\n"
                            f"❌ Failed: <code>{failed}</code>"
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            await asyncio.sleep(0.04)

        try:
            await bot.delete_message(chat_id=admin_chat_id, message_id=progress_message_id)
        except Exception:
            pass

        try:
            await bot.send_message(
                chat_id=admin_chat_id,
                text=(
                    f"✅ <b>Bonus Drop Complete!</b>\n\n"
                    f"• Total users targeted: <code>{total}</code>\n"
                    f"• Successfully sent: <code>{sent}</code>\n"
                    f"• Blocked/Invalid: <code>{blocked}</code>\n"
                    f"• Failed: <code>{failed}</code>\n\n"
                    f"Users can now claim via the button in their message."
                ),
                reply_markup=back_to_admin(),
                parse_mode="HTML"
            )
        except Exception as exc:
            logger.error("Failed to send bonus drop summary: %s", exc)

        try:
            await repository.log_admin_action(
                admin_id=admin_chat_id,
                action="bonus_drop_finish",
                target="all_users",
                details={"sent": sent, "blocked": blocked, "failed": failed, "drop_id": drop_id}
            )
        except Exception as exc:
            logger.error("Failed to log bonus drop finish: %s", exc)

    except Exception as exc:
        logger.exception("Bonus drop broadcast crashed: %s", exc)
        try:
            await bot.send_message(
                chat_id=admin_chat_id,
                text=f"❌ <b>Bonus Drop Failed!</b>\n\n<code>{escape_html(str(exc))}</code>",
                reply_markup=back_to_admin(),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ─── Drop Rain Claim Handler (user-facing) ─────────────────────────────────────

async def drop_rain_claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    parts = query.data.split(":")
    drop_id = parts[2]
    user_id = query.from_user.id

    repository = Repository(await get_db())
    drop_state = await repository.get_drop_rain_state()

    if not drop_state or drop_state.get("id") != drop_id or not drop_state.get("active"):
        await query.answer("❌ This bonus drop has expired!", show_alert=True)
        return

    if user_id in drop_state["claimed_user_ids"]:
        await query.answer("❌ You have already claimed this bonus!", show_alert=True)
        return

    if len(drop_state["claimed_user_ids"]) >= drop_state["max_claims"]:
        await query.answer("❌ Sorry, all bonus slots are filled!", show_alert=True)

        # If max reached, deactivate and notify admin
        if drop_state.get("active"):
            drop_state["active"] = False
            await repository.set_drop_rain_state(drop_state)
        return

    amount = drop_state["amount"]

    # Add to balance
    await repository.credit_balance(
        user_id=user_id,
        amount=amount,
        tx_type="bonus_drop",
        description=f"Bonus Drop #{drop_id}: {format_currency(amount)}"
    )

    # Track claim
    drop_state["claimed_user_ids"].append(user_id)
    if len(drop_state["claimed_user_ids"]) >= drop_state["max_claims"]:
        drop_state["active"] = False
    await repository.set_drop_rain_state(drop_state)

    # Delete the broadcast message
    try:
        await query.delete_message()
    except Exception:
        pass

    # Send congratulations
    bal = (await repository.get_user(user_id)).balance
    await context.bot.send_message(
        chat_id=user_id,
        text=(
            f"🎉 <b>Congratulations!</b>\n\n"
            f"✅ You have successfully claimed <code>{format_currency(amount)}</code>\n"
            f"from the <b>TaskHub Bonus Drop</b>! 💰\n\n"
            f"💰 <b>Your Balance:</b> <code>{format_currency(bal)}</code>\n\n"
            f"<blockquote>Keep completing tasks and inviting friends to earn more!</blockquote>"
        ),
        parse_mode="HTML"
    )

    await query.answer(f"✅ {format_currency(amount)} claimed successfully!", show_alert=True)


# ─── Regular Broadcast Handlers ────────────────────────────────────────────────

async def admin_broadcast_message_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data is None:
        return
    admin_state = context.user_data.get("admin_state", "")
    if admin_state != "awaiting_bc_message":
        return

    admin_chat_id = update.effective_user.id
    if not is_admin(admin_chat_id):
        return

    msg = update.message
    repository = Repository(await get_db())
    target = context.user_data.pop("bc_target", "all")
    context.user_data.pop("admin_state", None)

    if msg.text and msg.text.strip().lower() == "/cancel":
        await msg.reply_text("❌ Broadcast cancelled.", reply_markup=back_to_admin())
        return

    user_ids = []

    if target == "all":
        user_ids = await repository.get_all_user_ids()
    elif target == "active":
        now = datetime.now(IST)
        week_ago = (now - timedelta(days=7)).isoformat()
        all_users_model = await repository.get_all_users_cursor()
        for u in all_users_model:
            last_active = getattr(u, "last_active_date", "")
            if last_active and last_active >= week_ago:
                user_ids.append(u.user_id)
    elif target == "inactive":
        now = datetime.now(IST)
        week_ago = (now - timedelta(days=7)).isoformat()
        all_users_model = await repository.get_all_users_cursor()
        for u in all_users_model:
            last_active = getattr(u, "last_active_date", "")
            if not last_active or last_active < week_ago:
                user_ids.append(u.user_id)
    elif target == "bal":
        all_users_model = await repository.get_all_users_cursor()
        for u in all_users_model:
            if u.balance > 0:
                user_ids.append(u.user_id)

    if not user_ids:
        await msg.reply_text("❌ No target users found in this segment.", reply_markup=back_to_admin())
        return

    prog_msg = await msg.reply_text("📢 <b>Broadcast starting...</b>\n\nPreparing queue.", parse_mode="HTML")

    await repository.log_admin_action(
        admin_id=admin_chat_id,
        action="broadcast_start",
        target=target,
        details={"total_users": len(user_ids)}
    )

    message_to_copy = msg

    asyncio.create_task(
        Broadcaster.run_broadcast(
            bot=context.bot,
            repository=repository,
            admin_chat_id=admin_chat_id,
            progress_message_id=prog_msg.message_id,
            user_ids=user_ids,
            message_to_copy=message_to_copy,
            reply_markup=msg.reply_markup
        )
    )


async def admin_broadcast_abort_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return

    job_id = query.data.split(":")[3]
    cancelled = Broadcaster.cancel_job(job_id)

    if cancelled:
        await query.answer("🚨 Broadcast cancellation signal sent!", show_alert=True)
    else:
        await query.answer("❌ Job not found or already completed.", show_alert=True)
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass


# ─── Handler Registration ──────────────────────────────────────────────────────

def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(admin_broadcast_menu_handler, pattern="^admin:broadcast_menu$"))
    application.add_handler(CallbackQueryHandler(admin_broadcast_start_handler, pattern="^admin:bc_start:(all|active|inactive|bal|drop_rain)$"))
    application.add_handler(CallbackQueryHandler(admin_broadcast_abort_handler, pattern="^admin:bc_abort:[a-f0-9]+$"))

    # Drop rain claim from user side
    application.add_handler(CallbackQueryHandler(drop_rain_claim_handler, pattern="^drop_rain:claim:[a-f0-9]+$"))

    # Admin message receiver for regular broadcasts
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        admin_broadcast_message_receiver
    ), group=4)

    # Admin text handler for drop rain config
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        admin_drop_rain_config_handler
    ), group=5)
