"""
helpers.py — Date/time helpers (IST), conversion utils, and other helpers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_now() -> datetime:
    """Get the current time in IST (Indian Standard Time)."""
    return datetime.now(IST)


def get_ist_now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Get the current time as a formatted string in IST."""
    return datetime.now(IST).strftime(fmt)


def format_ist_iso(dt: Optional[datetime] = None) -> str:
    """Format a datetime (or current time if None) as an ISO string."""
    if dt is None:
        dt = datetime.now(IST)
    elif dt.tzinfo is None:
        # Assume naive datetime is in IST
        dt = dt.replace(tzinfo=IST)
    else:
        dt = dt.astimezone(IST)
    return dt.isoformat()


def parse_ist_iso(iso_str: str) -> datetime:
    """Parse an ISO string to a datetime object, ensuring it's in IST."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=IST)
        return dt.astimezone(IST)
    except Exception as exc:
        logger.error("Failed to parse ISO string %s: %s", iso_str, exc)
        return datetime.now(IST)


async def edit_or_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: Optional[Any] = None,
    image_url: Optional[str] = None,
    parse_mode: str = "HTML",
    media_type: str = "photo",
) -> None:
    """
    Seamlessly transition the user interface by editing the existing message
    (either text or caption/media of a photo/video) or sending a new message/media if editing fails.
    """
    from telegram import InputMediaPhoto, InputMediaVideo
    from telegram.error import BadRequest

    query = update.callback_query
    chat_id = update.effective_chat.id if update.effective_chat else None
    
    if query:
        # User clicked an inline button
        try:
            msg = query.message
            has_media = bool(msg and (msg.photo or msg.video))

            if image_url:
                if has_media:
                    # Update existing photo/video and caption
                    if media_type == "video":
                        media = InputMediaVideo(media=image_url, caption=text, parse_mode=parse_mode)
                    else:
                        media = InputMediaPhoto(media=image_url, caption=text, parse_mode=parse_mode)
                    await query.edit_message_media(
                        media=media,
                        reply_markup=reply_markup
                    )
                else:
                    # Current message has no media, delete it and send photo/video
                    try:
                        await query.delete_message()
                    except Exception:
                        pass
                    if media_type == "video":
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=image_url,
                            caption=text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
                    else:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=image_url,
                            caption=text,
                            reply_markup=reply_markup,
                            parse_mode=parse_mode
                        )
            else:
                if has_media:
                    # Update caption only, leave media unchanged
                    await query.edit_message_caption(
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                else:
                    # Edit plain text message
                    await query.edit_message_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        disable_web_page_preview=True
                    )
            # Acknowledge the click
            try:
                await query.answer()
            except Exception:
                pass
            return
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                # Safe to ignore
                try:
                    await query.answer()
                except Exception:
                    pass
                return
            logger.warning("Failed to edit inline message, falling back to new message: %s", e)
            try:
                await query.delete_message()
            except Exception:
                pass

    # Fallback/New Message Flow (no callback query, or edit failed)
    if chat_id:
        if image_url:
            try:
                if media_type == "video":
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=image_url,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=image_url,
                        caption=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
            except Exception:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode,
                        disable_web_page_preview=True
                    )
                except Exception:
                    pass
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )

