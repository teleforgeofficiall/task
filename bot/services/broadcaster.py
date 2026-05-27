"""
broadcaster.py — High-performance async broadcast engine.
Supports cancel mid-flight, real-time progress editing, and RetryAfter/flood handling.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import List, Optional, Any
from telegram import Message, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import RetryAfter, Forbidden, BadRequest, TelegramError

from bot.database.repository import Repository
from bot.keyboards.admin_kb import broadcast_cancel_keyboard, back_to_admin

logger = logging.getLogger(__name__)

# Global registry of active broadcast jobs
# job_id -> is_cancelled (bool)
active_broadcast_jobs: dict[str, bool] = {}


class Broadcaster:
    """Async broadcaster engine supporting cancellation and rate-limit backing off."""

    @staticmethod
    def cancel_job(job_id: str) -> bool:
        """Mark a broadcast job as cancelled. Returns True if job was registered."""
        if job_id in active_broadcast_jobs:
            active_broadcast_jobs[job_id] = True
            logger.info("Broadcast job %s marked for cancellation.", job_id)
            return True
        return False

    @staticmethod
    async def run_broadcast(
        bot,
        repository: Repository,
        admin_chat_id: int,
        progress_message_id: int,
        user_ids: List[int],
        message_to_copy: Optional[Message] = None,
        custom_text: Optional[str] = None,
        custom_photo: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """
        Main broadcast runner loop.
        Sends messages to users in list, respects Telegram rate limits,
        and periodically edits the admin's progress message.
        """
        job_id = str(uuid.uuid4())[:8]
        active_broadcast_jobs[job_id] = False

        total_users = len(user_ids)
        sent = 0
        blocked = 0
        failed = 0
        current_index = 0

        # Update progress keyboard with cancel button targeting this job_id
        cancel_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚨 Cancel Broadcast", callback_data=f"admin:bc_abort:{job_id}")]
        ])

        try:
            # Let the admin know the broadcast has started
            await bot.edit_message_text(
                chat_id=admin_chat_id,
                message_id=progress_message_id,
                text=(
                    f"📢 <b>Broadcast Started!</b>\n\n"
                    f"Target: <code>{total_users}</code> users.\n"
                    f"Status: ⏳ Preparing messages..."
                ),
                reply_markup=cancel_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass

        for user_id in user_ids:
            # 1. Check if broadcast was cancelled mid-flight
            if active_broadcast_jobs.get(job_id) is True:
                logger.info("Broadcast job %s aborted by admin.", job_id)
                break

            current_index += 1
            success = False
            retries = 3

            while retries > 0:
                try:
                    if message_to_copy:
                        # Copy original message exactly
                        await bot.copy_message(
                            chat_id=user_id,
                            from_chat_id=message_to_copy.chat_id,
                            message_id=message_to_copy.message_id,
                            reply_markup=reply_markup or message_to_copy.reply_markup
                        )
                    elif custom_photo:
                        # Send text + photo
                        await bot.send_photo(
                            chat_id=user_id,
                            photo=custom_photo,
                            caption=custom_text,
                            reply_markup=reply_markup,
                            parse_mode="HTML"
                        )
                    else:
                        # Plain text message
                        await bot.send_message(
                            chat_id=user_id,
                            text=custom_text,
                            reply_markup=reply_markup,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                    success = True
                    sent += 1
                    break
                except RetryAfter as e:
                    # Respect API limits: wait and try again
                    logger.warning("Rate limit hit during broadcast. Sleeping for %.2f seconds.", e.retry_after)
                    await asyncio.sleep(e.retry_after)
                    retries -= 1
                except Forbidden:
                    # User blocked the bot
                    blocked += 1
                    break
                except BadRequest as e:
                    # User deleted account or chat not found
                    if "chat not found" in str(e).lower() or "user_id is invalid" in str(e).lower():
                        blocked += 1
                    else:
                        logger.error("BadRequest in broadcast to user %d: %s", user_id, e)
                        failed += 1
                    break
                except TelegramError as e:
                    logger.error("TelegramError in broadcast to user %d: %s", user_id, e)
                    failed += 1
                    break
                except Exception as exc:
                    logger.error("Unexpected error broadcasting to user %d: %s", user_id, exc)
                    failed += 1
                    break

            # 2. Update progress every 25 sends or at the end
            if current_index % 25 == 0 or current_index == total_users:
                try:
                    pct = (current_index / total_users) * 100
                    prog_text = (
                        f"📢 <b>Broadcast Progress ({pct:.1f}%)</b>\n\n"
                        f"Total Target: <code>{total_users}</code>\n"
                        f"Processed: <code>{current_index}/{total_users}</code>\n"
                        f"✅ Sent: <code>{sent}</code>\n"
                        f"🚫 Blocked/Inactive: <code>{blocked}</code>\n"
                        f"❌ Failed: <code>{failed}</code>\n\n"
                        f"<i>Sending messages asynchronously...</i>"
                    )
                    
                    # If this is the final update, remove the cancel button
                    kb = cancel_kb if current_index < total_users else None
                    await bot.edit_message_text(
                        chat_id=admin_chat_id,
                        message_id=progress_message_id,
                        text=prog_text,
                        reply_markup=kb,
                        parse_mode="HTML"
                    )
                except Exception as exc:
                    logger.debug("Failed to update broadcast status message: %s", exc)

            # Limit sending rate: small throttle to avoid aggressive bursting
            await asyncio.sleep(0.04)

        # 3. Final summary
        aborted = active_broadcast_jobs.get(job_id) is True
        active_broadcast_jobs.pop(job_id, None)

        status_prefix = "🚨 <b>Broadcast Cancelled!</b>" if aborted else "✅ <b>Broadcast Completed!</b>"
        summary_text = (
            f"{status_prefix}\n\n"
            f"<b>Final Results:</b>\n"
            f"• Target Users: <code>{total_users}</code>\n"
            f"• Processed: <code>{current_index}</code>\n"
            f"• Sent: <code>{sent}</code>\n"
            f"• Blocked (Bot Blocked): <code>{blocked}</code>\n"
            f"• Failed (API Errors): <code>{failed}</code>"
        )

        try:
            await bot.send_message(
                chat_id=admin_chat_id,
                text=summary_text,
                reply_markup=back_to_admin(),
                parse_mode="HTML"
            )
            # Delete intermediate progress message to clean up chat log
            await bot.delete_message(chat_id=admin_chat_id, message_id=progress_message_id)
        except Exception as e:
            # Fallback edit progress message directly if final delete/send fails
            try:
                await bot.edit_message_text(
                    chat_id=admin_chat_id,
                    message_id=progress_message_id,
                    text=summary_text,
                    reply_markup=back_to_admin(),
                    parse_mode="HTML"
                )
            except Exception:
                pass

        # Log to Admin Logs
        await repository.log_admin_action(
            admin_id=admin_chat_id,
            action="broadcast_finish",
            target="all_users",
            details={
                "total": total_users,
                "sent": sent,
                "blocked": blocked,
                "failed": failed,
                "cancelled": aborted
            }
        )
