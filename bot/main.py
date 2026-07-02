"""
main.py — Application entry point.
Bootstraps python-telegram-bot and FastAPI into a unified event loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response, status
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder

from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, TypeHandler

from bot.database import close_db, check_db_health, Repository, init_db, get_session
from bot.middlewares.rate_limiter import setup_rate_limiter
from bot.handlers import register_user_handlers
from bot.admin import register_admin_handlers
from bot.callbacks.router import register_router
from bot.api.admin import router as admin_router
from bot.services.referral import check_referral_success

from config.settings import settings

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Avoid leaking bot token in logs (httpx logs full request URLs by default).
logging.getLogger("httpx").setLevel(logging.WARNING)

# Initialize PTB Application
ptb_app = ApplicationBuilder().token(settings.BOT_TOKEN).build()


async def global_error_handler(update: object, context: object) -> None:
    """Log all exceptions without crashing the bot."""
    from telegram.error import BadRequest, Forbidden, NetworkError, TimedOut
    exc = context.error if hasattr(context, 'error') else None
    if isinstance(exc, (BadRequest, Forbidden, NetworkError, TimedOut, TelegramError)):
        logger.warning("PTB handler warning (%s): %s", type(exc).__name__, exc)
    else:
        logger.exception("PTB handler error: %s", exc)


ptb_app.add_error_handler(global_error_handler)

# ─── Maintenance Mode ─────────────────────────────────────────────────────
# Toggle ON/OFF from admin panel setting "maintenance_mode".
# When ON → ALL users are blocked with maintenance message.
# When OFF → normal operation (middleware passes through).

async def maintenance_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Block all users when maintenance_mode is ON."""
    if not update.effective_user:
        return

    from bot.database import get_db, Repository
    try:
        db = await get_db()
        repo = Repository(db)
        maintenance_on = await repo.get_setting("maintenance_mode", False)
    except Exception:
        return  # If DB fails, allow through (don't break the bot)

    if not maintenance_on:
        return  # Maintenance OFF — allow all

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔧 <b>Maintenance Mode</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bot abhi maintenance me hai.\n"
        "Baad mein /start karna.\n\n"
        "Dhanyavaad! 🙏"
    )

    if update.callback_query:
        await update.callback_query.answer("Maintenance mode", show_alert=True)
        try:
            await update.callback_query.edit_message_text(text, parse_mode="HTML")
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_user.id, text=text, parse_mode="HTML"
            )
    elif update.message:
        await update.message.reply_text(text, parse_mode="HTML")

    raise ApplicationHandlerStop()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles async startup and shutdown hooks cleanly."""
    try:
        _webhook_url = settings.WEBHOOK_URL

        # Ensure database and user exist (MySQL only)
        from bot.database.session import ensure_database_exists
        await ensure_database_exists()

        # Initialize database tables and defaults
        await init_db()
        async with get_session() as session:
            repository = Repository(session)
            await repository.ensure_defaults()

        # Load admin IDs cache from DB
        from bot.admin.panel import refresh_admin_ids
        await refresh_admin_ids()

        # Setup PTB Handlers and Middlewares
        setup_rate_limiter(ptb_app)
        ptb_app.add_handler(TypeHandler(Update, maintenance_middleware), group=-1)
        register_user_handlers(ptb_app)
        register_admin_handlers(ptb_app)
        register_router(ptb_app)

        # Telegram startup (optional for local verification)
        if settings.DISABLE_TELEGRAM_NETWORK:
            logger.warning(
                "DISABLE_TELEGRAM_NETWORK=1 -> skipping PTB initialize/start and webhook/polling startup."
            )
        else:
            # Start bot application (valid BOT_TOKEN required)
            await ptb_app.initialize()
            await ptb_app.bot.set_my_commands([
                BotCommand("start", "🚀 Let's start your earning journey"),
                BotCommand("help", "🆘 Get help & support"),
                BotCommand("promote", "📢 Promote your app/website/bot"),
                BotCommand("admin", "🛠️ Go to the admin panel"),
            ])
            await ptb_app.start()

            # Start listening for updates
            if _webhook_url:
                webhook_uri = f"{_webhook_url}/webhook"
                await ptb_app.bot.set_webhook(
                    url=webhook_uri,
                    secret_token=settings.WEBHOOK_SECRET if settings.WEBHOOK_SECRET else None
                )
                logger.info("Webhook endpoint registered: %s", webhook_uri)
            else:
                await ptb_app.bot.delete_webhook()
                await ptb_app.updater.start_polling()
                logger.info("Long polling cycle started.")

        yield

    finally:
        # Stop bot application gracefully
        logger.info("Stopping bot service...")
        if not settings.DISABLE_TELEGRAM_NETWORK:
            try:
                if not _webhook_url:
                    await ptb_app.updater.stop()
                await ptb_app.stop()
                await ptb_app.shutdown()
            except Exception as exc:
                logger.debug("PTB shutdown skipped/failed (non-fatal): %s", exc)
        
        # Close database connections
        await close_db()
        logger.info("Application shut down successfully.")


# Initialize FastAPI app
app = FastAPI(
    title="TASKHUB Backend",
    version="1.0.0",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/opt/taskhub/uploads"

app.include_router(admin_router)


@app.get("/")
async def root():
    return Response(content="Bot is Running", media_type="text/plain")

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Render deployment."""
    db_healthy = await check_db_health()
    return {
        "ok": True,
        "status": "healthy" if db_healthy else "degraded",
        "service": "taskhub-backend",
        "database": "connected" if db_healthy else "disconnected",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/api/health/db")
async def db_health_detail():
    """Detailed DB health check."""
    db_healthy = await check_db_health()
    return {
        "database": "connected" if db_healthy else "disconnected",
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "name": settings.DB_NAME,
    }


@app.get("/api/user/{user_id}")
async def api_user_info(user_id: int):
    """Return user profile info for device verification page."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
    if not user:
        return {"ok": False, "error": "User not found"}
    try:
        photos = await ptb_app.bot.get_user_profile_photos(user_id, limit=1)
        if photos.photos:
            f = await ptb_app.bot.get_file(photos.photos[0][-1].file_id)
            pfp_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{f.file_path}" if f.file_path else ""
        else:
            pfp_url = ""
    except Exception:
        pfp_url = ""
    return {
        "ok": True,
        "user": {
            "id": user.user_id,
            "first_name": user.first_name,
            "username": user.username,
            "pfp_url": pfp_url,
        },
    }


@app.post("/api/verify-device")
async def api_verify_device(request: Request):
    """Store device fingerprint and verify device uniqueness."""
    from bot.database import get_session, Repository
    from bot.database.models_sql import UserTable
    from sqlalchemy import select
    from fastapi import HTTPException
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    device_hash = data.get("device_hash")
    user_id = data.get("user_id")
    if not device_hash or not user_id:
        raise HTTPException(status_code=400, detail="Missing device_hash or user_id")
    async with get_session() as session:
        repo = Repository(session)

        # Gate 1: User exists?
        result = await session.execute(select(UserTable).where(UserTable.user_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return {"ok": False, "error": "user_not_found"}
        if user.device_verified:
            return {"ok": False, "error": "already_verified"}

        # Gate 2: Device hash already linked to a different user?
        existing_user = await repo.get_device_fingerprint_user(device_hash)
        if existing_user is not None:
            return {"ok": False, "error": "device_linked", "existing_user": existing_user}

        success = await repo.store_device_fingerprint(device_hash, user_id)
        if not success:
            return {"ok": False, "error": "storage_failed"}
        return {"ok": True, "message": "Device verified"}


@app.post("/api/verification-done")
async def api_verification_done(request: Request):
    """Called by mini app after successful verification, just before closing."""
    from bot.database import get_session, Repository
    from bot.keyboards.user_kb import miniapp_keyboard
    try:
        data = await request.json()
    except Exception:
        return {"ok": False}
    user_id = data.get("user_id")
    if not user_id:
        return {"ok": False}
    try:
        async with get_session() as session:
            repo = Repository(session)
            miniapp_url = await repo.get_setting("miniapp_url", "https://taskhub-khaki.vercel.app")
            separator = "&" if "?" in miniapp_url else "?"
            miniapp_url = f"{miniapp_url}{separator}_cb={int(time.time())}"
            congrats_text = (
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "🎉 <b>Congratulations!</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Welcome to <b>TaskHub</b>! You now have full access.\n\n"
                "Open the MiniApp below to start earning:\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💸 Complete Tasks & Earn\n"
                "🎮 Play Games & Win\n"
                "👥 Refer Friends for Commission\n"
                "💰 Withdraw to UPI / Stars\n"
                "━━━━━━━━━━━━━━━━━━━━━━"
            )
            kb = miniapp_keyboard(miniapp_url)
            if not settings.DISABLE_TELEGRAM_NETWORK:
                await ptb_app.bot.send_message(
                    chat_id=user_id, text=congrats_text,
                    reply_markup=kb, parse_mode="HTML"
                )
            else:
                logger.warning("verification-done: DISABLE_TELEGRAM_NETWORK is on, skipping send_message")
            # Delete the stored verify message from DB
            verify_msg_id = await repo.get_setting(f"verify_msg:{user_id}")
            if verify_msg_id:
                try:
                    await ptb_app.bot.delete_message(chat_id=user_id, message_id=int(verify_msg_id))
                except Exception:
                    pass
                await repo.update_setting(f"verify_msg:{user_id}", None)
        return {"ok": True}
    except Exception as exc:
        logger.exception("verification-done: error for user %s: %s", user_id, exc)
        return {"ok": False, "error": "Server error"}


async def _get_tg_file_path(user_id: int) -> str | None:
    """Get Telegram file_path for user's profile photo using raw Bot API (no ptb_app dependency)."""
    import httpx
    try:
        token = settings.BOT_TOKEN
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/getUserProfilePhotos",
                json={"user_id": user_id, "limit": 1}
            )
            d = r.json()
            if not d.get("ok") or not d["result"]["total_count"]:
                return None
            file_id = d["result"]["photos"][0][-1]["file_id"]
            r = await client.post(
                f"https://api.telegram.org/bot{token}/getFile",
                json={"file_id": file_id}
            )
            d = r.json()
            if not d.get("ok"):
                return None
            return d["result"]["file_path"]
    except Exception:
        return None


@app.get("/api/user/{user_id}/photo")
async def api_user_photo(user_id: int):
    """Return downloadable URL for user's profile photo."""
    try:
        file_path = await _get_tg_file_path(user_id)
        if not file_path:
            return {"ok": False, "error": "No photo"}
        return {"ok": True, "url": f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/user/{user_id}/pfp")
async def api_user_pfp(user_id: int):
    """Proxy user's Telegram profile photo — fetches fresh via raw Bot API."""
    import httpx
    try:
        file_path = await _get_tg_file_path(user_id)
        if not file_path:
            return Response(status_code=404)
        url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return Response(status_code=404)
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=3600"}
            )
    except Exception:
        return Response(status_code=404)


async def _serve_device_html(bot_username: str = "") -> Response:
    """Read device.html and inject bot username."""
    import os
    html_path = os.path.join(os.path.dirname(__file__), "..", "vercel", "device.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = "<html><body><h2>Verification page not found</h2></body></html>"
    html = html.replace("__BOT_USERNAME__", bot_username)
    return Response(content=html, media_type="text/html")

@app.get("/verify/{user_id}")
async def verify_page(user_id: int):
    """Serve the device verification HTML page with bot username injected."""
    bot_username = ""
    try:
        bot_user = await ptb_app.bot.get_me()
        bot_username = bot_user.username or ""
    except Exception:
        pass
    return await _serve_device_html(bot_username)

@app.get("/device.html")
async def device_page(user_id: int = 0):
    """Serve device verification HTML page (query-param based)."""
    bot_username = ""
    try:
        bot_user = await ptb_app.bot.get_me()
        bot_username = bot_user.username or ""
    except Exception:
        pass
    return await _serve_device_html(bot_username)


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Telegram Webhook Update Endpoint."""
    if settings.WEBHOOK_SECRET:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != settings.WEBHOOK_SECRET:
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    # Local/dev verification mode: allow FastAPI to run without PTB network initialisation.
    if settings.DISABLE_TELEGRAM_NETWORK:
        return Response(status_code=status.HTTP_200_OK)
            
    try:
        body = await request.json()
        update = Update.de_json(body, ptb_app.bot)
        await ptb_app.process_update(update)
    except Exception as exc:
        logger.exception("Failed to process webhook update: %s", exc)
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    return Response(status_code=status.HTTP_200_OK)


# =========================================================================
# MINI APP API
# =========================================================================

@app.get("/api/app/init")
async def app_init(user_id: int, init_data: str = "", hash: str = "", startapp: str = ""):
    """Initialize the Mini App - check user, channels, welcome bonus."""
    try:
        from bot.database import get_session, Repository
        from bot.middlewares.auth import get_unjoined_channels
        async with get_session() as session:
            repo = Repository(session)
            user = await repo.get_user(user_id)
            if not user:
                referrer_id = None
                if startapp:
                    try:
                        sid = None
                        if startapp.startswith("ref_"):
                            parts = startapp.split("_")
                            if len(parts) >= 2:
                                sid = int(parts[1])
                        else:
                            sid = int(startapp)
                        if sid and sid != user_id:
                            ref_user = await repo.get_user(sid)
                            if ref_user and not ref_user.banned:
                                referrer_id = sid
                    except (ValueError, TypeError, IndexError):
                        pass
                user = await repo.create_user(user_id, "User", "User", referrer=referrer_id)
            from bot.admin.panel import get_admin_ids
            is_admin = user_id in get_admin_ids()
            channels_unjoined = []
            if not settings.DISABLE_TELEGRAM_NETWORK:
                try:
                    channels_unjoined = await asyncio.wait_for(
                        get_unjoined_channels(ptb_app.bot, user_id, repo),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("app_init: get_unjoined_channels timed out for user %s", user_id)
                except Exception as exc:
                    logger.warning("app_init: get_unjoined_channels failed: %s", exc)
            welcome_bonus_claimed = await repo.get_setting("welcome_bonus_claimed_" + str(user_id), False)
            try:
                pfp = ""
                meta = dict(user.user_meta or {})
                cached_pfp = meta.get("pfp_url", "")
                cached_at = meta.get("pfp_cached_at", 0)
                cache_age = time.time() - cached_at if cached_at else float('inf')
                use_cache = cached_pfp and cache_age < 1800
                if use_cache:
                    pfp = f"/api/user/{user_id}/pfp"
                else:
                    try:
                        file_path = await _get_tg_file_path(user_id)
                        if file_path:
                            meta["pfp_url"] = file_path
                            meta["pfp_cached_at"] = time.time()
                            await repo.update_user_fields(user_id, user_meta=meta)
                            pfp = f"/api/user/{user_id}/pfp"
                    except Exception as e:
                        logger.warning("app_init: Telegram PFP fetch failed for %s: %s", user_id, e)
            except Exception as exc:
                logger.warning("app_init: profile photo failed: %s", exc)
                pfp = ""
            return {
                "ok": True,
                "user": {
                    "id": user.user_id,
                    "first_name": user.first_name,
                    "username": user.username,
                    "balance": float(user.balance or 0),
                    "pfp": pfp,
                    "upi": meta.get("upi", ""),
                    "banned": user.banned,
                },
                "is_admin": is_admin,
                "channels_unjoined": [{"id": c.get("id"), "title": c.get("title", "Channel")} for c in channels_unjoined],
                "welcome_bonus_claimed": welcome_bonus_claimed,
                "welcome_bonus": float(await repo.get_setting("welcome_bonus_amount", 5)),
            }
    except Exception as exc:
        logger.exception("app_init: unhandled error for user %s: %s", user_id, exc)
        return {"ok": False, "error": "Server error. Please try again later."}


@app.get("/api/app/debug")
async def app_debug(user_id: int = 0):
    """Return debug info about MiniApp settings."""
    from bot.database import get_session, Repository
    try:
        async with get_session() as session:
            repo = Repository(session)
            miniapp_url = await repo.get_setting("miniapp_url", "https://taskhub-khaki.vercel.app")
            verif_url = await repo.get_setting("device_verification_url", "")
            dev_enabled = await repo.get_setting("device_verification_enabled", False)
            user = await repo.get_user(user_id) if user_id else None
            return {
                "ok": True,
                "miniapp_url": miniapp_url,
                "device_verification_url": verif_url,
                "device_verification_enabled": dev_enabled,
                "user_found": user is not None,
            }
    except Exception as exc:
        logger.exception("debug endpoint error: %s", exc)
        return {"ok": False, "error": str(exc)}


@app.get("/api/app/check-channels")
async def app_check_channels(user_id: int):
    """Verify user has joined all required channels."""
    from bot.database import get_session, Repository
    from bot.middlewares.auth import get_unjoined_channels
    if settings.DISABLE_TELEGRAM_NETWORK:
        return {"ok": True, "all_joined": True, "joined": []}
    async with get_session() as session:
        repo = Repository(session)
        try:
            unjoined = await asyncio.wait_for(
                get_unjoined_channels(ptb_app.bot, user_id, repo),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning("check-channels: timeout for user %s", user_id)
            unjoined = []
        except Exception as exc:
            logger.warning("check-channels: failed for user %s: %s", user_id, exc)
            unjoined = []
        all_joined = len(unjoined) == 0
        joined = []
        if not all_joined:
            channels = await repo.get_fsub_channels()
            for ch in channels:
                if ch.get("id") not in [u.get("id") for u in unjoined]:
                    joined.append(ch.get("id"))
        return {"ok": True, "all_joined": all_joined, "joined": joined}


@app.post("/api/app/claim-bonus")
async def app_claim_bonus(request: Request):
    """Claim welcome bonus."""
    from bot.database import get_session, Repository
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    if not user_id:
        return {"ok": False, "error": "Missing user_id"}
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        amount = float(await repo.get_setting("welcome_bonus_amount", 5))
        already_claimed = await repo.get_setting("welcome_bonus_claimed_" + str(user_id), False)
        if already_claimed:
            return {"ok": False, "error": "Welcome bonus already claimed"}
        await repo.credit_balance(user_id, amount, "welcome_bonus", "Welcome bonus via Mini App")
        await repo.update_setting("welcome_bonus_claimed_" + str(user_id), True)
        return {"ok": True, "amount": amount}


@app.get("/api/app/tasks")
async def app_tasks(user_id: int):
    """Get all available tasks for the Mini App."""
    from bot.database import get_session, Repository
    try:
        async with get_session() as session:
            repo = Repository(session)
            tasks = await repo.get_active_tasks()
            user = await repo.get_user(user_id)
            completed_tasks = list(user.completed_tasks or []) if user else []
            pending_proofs = await repo.get_user_pending_proofs(user_id)
            pending_task_ids = {p["task_id"] for p in pending_proofs}
            result = []
            for t in tasks:
                result.append({
                    "id": t.id,
                    "title": (t.description.split('\n')[0][:80] if t.description else "Task") if isinstance(t.description, str) else "Task",
                    "description": t.description or "",
                    "reward": float(t.reward),
                    "type": t.task_type or "manual",
                    "icon": "📋",
                    "image": f"/api/app/task-image/{t.id}" if t.image else "",
                    "task_image": t.task_image or "",
                    "color": t.color or "#7b5ef8",
                    "color2": t.color2 or "#5a3fd6",
                    "completions": t.completion_count or 0,
                    "is_completed": t.id in completed_tasks,
                    "has_pending_proof": t.id in pending_task_ids,
                    "guide": t.guide or "",
                    "channel_url": t.channel_url or "",
                    "channel_title": t.channel_title or "",
                    "video_url": t.video_url or "",
                    "steps": t.steps or [],
                    "is_multi_reward": t.is_multi_reward or False,
                    "offer_url": t.offer_url or "",
                })
            return {"ok": True, "tasks": result}
    except Exception as e:
        logger.error("app_tasks failed for user %s: %s", user_id, e, exc_info=True)
        return {"ok": False, "error": "Failed to load tasks"}


@app.get("/api/app/task/{task_id}")
async def app_task_detail(task_id: int, user_id: int):
    """Get task details."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        t = await repo.get_task(task_id)
        if not t:
            return {"ok": False, "error": "Task not found"}
        user = await repo.get_user(user_id)
        completed_tasks = list(user.completed_tasks or []) if user else []
        return {
            "ok": True,
            "task": {
                "id": t.id,
                "title": (t.description.split('\n')[0][:80] if t.description else "Task") if isinstance(t.description, str) else "Task",
                "description": t.description or "",
                "reward": float(t.reward),
                "type": t.task_type or "manual",
                "icon": "📋",
                "image": f"/api/app/task-image/{t.id}" if t.image else "",
                "task_image": t.task_image or "",
                "color": t.color or "#7b5ef8",
                "color2": t.color2 or "#5a3fd6",
                "completions": t.completion_count or 0,
                "is_completed": t.id in completed_tasks,
                "has_pending_proof": await repo.has_pending_proof(user_id, task_id),
                "guide": t.guide or "",
                "channel_title": t.channel_title or "",
                "channel_url": t.channel_url or "",
                "video_url": t.video_url or "",
                "steps": t.steps or [],
                "is_multi_reward": t.is_multi_reward or False,
                "offer_url": t.offer_url or "",
            }
        }


@app.post("/api/app/task/{task_id}/verify-channel")
async def app_verify_channel_task(task_id: int, request: Request):
    """Auto-verify channel task membership and credit reward instantly."""
    from bot.database import get_session, Repository
    from bot.middlewares.auth import check_channel_membership
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    if not user_id:
        return {"ok": False, "error": "Missing user_id"}
    async with get_session() as session:
        repo = Repository(session)
        task = await repo.get_task(task_id)
        if not task:
            return {"ok": False, "error": "Task not found"}
        if task.task_type != "channel":
            return {"ok": False, "error": "Not a channel task"}
        user = await repo.get_user(user_id)
        completed_tasks = list(user.completed_tasks or [])
        if task_id in completed_tasks:
            return {"ok": False, "error": "Already completed"}
        if not task.is_active:
            return {"ok": False, "error": "Task is not active"}
        logger.info("verify-channel: task=%d channel_id=%r channel_url=%r", task_id, task.channel_id, task.channel_url)
        if not task.channel_id or not str(task.channel_id).strip():
            return {"ok": False, "error": "Channel ID not configured. Admin must set Channel ID when editing this task.", "channel_url": task.channel_url or ""}
        joined = await check_channel_membership(ptb_app.bot, user_id, task.channel_id)
        if not joined:
            return {"ok": False, "error": "You haven't joined the channel yet, or the bot needs admin access. Please join and try again.", "channel_url": task.channel_url or ""}
        await repo.credit_balance(
            user_id=user_id, amount=task.reward,
            tx_type="task_reward", description=f"Task #{task.id} completed",
            ref_id=str(task.id)
        )
        c = list(user.completed_tasks or [])
        if task_id not in c:
            c.append(task_id)
        await repo.update_user_fields(user_id, completed_tasks=c)
        await repo.increment_task_completion(task_id)
        user = await repo.get_user(user_id)
        # Referral reward check — uses shared check_referral_success logic
        try:
            await check_referral_success(repo, user_id, ptb_app.bot)
        except Exception as e:
            logger.error("Failed to check referral reward: %s", e)
        return {"ok": True, "balance": float(user.balance or 0), "reward": float(task.reward), "message": f"Task completed! ₹{float(task.reward)} credited!"}


async def _notify_admins_proof(proof_id: int, user_id: int, task_id: int, task_desc: str, reward: float, proof_image: str):
    """Notify all admins about a new proof submission via Telegram bot."""
    import base64, io
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.admin.panel import get_admin_ids
    admin_ids = get_admin_ids()
    if not admin_ids:
        return
    caption = (
        f"📝 <b>New Proof Submission — #{proof_id}</b>\n"
        f"─────────────────────\n"
        f"👤 <b>User:</b> ID <code>{user_id}</code>\n"
        f"💸 <b>Task:</b> {task_desc[:100]} (#{task_id})\n"
        f"💰 <b>Reward:</b> <code>₹{reward:.2f}</code>\n"
        f"─────────────────────\n"
        f"<i>Review the screenshot below and take action.</i>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:proof_decide:approve:{proof_id}:0"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:proof_decide:reject:{proof_id}:0"),
        ],
        [
            InlineKeyboardButton("❌ Reject with Reason", callback_data=f"admin:proof_reason:{proof_id}:0"),
        ]
    ])
    for aid in admin_ids:
        try:
            if proof_image.startswith('data:'):
                _h, encoded = proof_image.split(',', 1)
                buf = io.BytesIO(base64.b64decode(encoded))
            else:
                buf = proof_image
            await ptb_app.bot.send_photo(chat_id=aid, photo=buf, caption=caption, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.warning("Failed to send proof notification to admin %s: %s", aid, e)


@app.post("/api/app/task/{task_id}/submit")
async def app_submit_proof(task_id: int, request: Request):
    """Submit task proof from Mini App - admin will review before marking complete."""
    from bot.database import get_session, Repository
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    proof_image = data.get("proof_image", "")
    txn_id = data.get("txn_id", "")
    upi = data.get("upi", "")
    if not user_id:
        return {"ok": False, "error": "Missing user_id"}
    if not proof_image and not txn_id:
        return {"ok": False, "error": "Please provide proof screenshot or transaction ID"}
    proof_image = (proof_image or "")[:1000000]
    async with get_session() as session:
        repo = Repository(session)
        task = await repo.get_task(task_id)
        if not task:
            return {"ok": False, "error": "Task not found"}
        user = await repo.get_user(user_id)
        completed_tasks = list(user.completed_tasks or [])
        if task_id in completed_tasks:
            return {"ok": False, "error": "Already completed"}
        if await repo.has_pending_proof(user_id, task_id):
            return {"ok": False, "error": "Proof already submitted, awaiting review"}
        try:
            proof = await repo.add_proof(user_id, task_id, proof_image, "photo")
        except Exception as exc:
            logger.exception("add_proof failed for user %s task %s: %s", user_id, task_id, exc)
            return {"ok": False, "error": "Failed to save proof. Try a smaller image."}
        # Notify admins about new proof
        if proof_image:
            asyncio.create_task(_notify_admins_proof(
                proof.id if hasattr(proof, 'id') else 0,
                user_id, task_id, task.description if task else "",
                float(task.reward) if task else 0, proof_image
            ))
        # Save UPI for payout if provided
        if upi:
            meta = dict(user.user_meta or {})
            meta["upi"] = upi
            await repo.update_user_fields(user_id, user_meta=meta)
        # Store txn_id in proof details via settings (simple storage)
        if txn_id:
            await repo.update_setting(f"proof_txn:{user_id}:{task_id}", txn_id)
        return {"ok": True, "message": "Proof submitted! Admin will review and approve."}


@app.get("/api/app/bonus")
async def app_bonus(user_id: int):
    """Get daily bonus status."""
    from bot.database import get_session, Repository
    import datetime
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        enabled = await repo.get_setting("streak_bonus_enabled", True)
        if not enabled:
            return {"ok": False, "error": "Streak bonus disabled"}
        last_bonus = user.last_bonus_date
        today = datetime.date.today().isoformat()
        can_claim = last_bonus != today
        meta = user.user_meta or {}
        bonus_streak = meta.get("bonus_streak", 0)
        amounts = await repo.get_setting("streak_bonus_amounts", [1, 1.5, 2, 2.5, 3, 5, 10])
        if can_claim:
            day = (bonus_streak % len(amounts)) + 1
        else:
            day = ((bonus_streak - 1) % len(amounts)) + 1 if bonus_streak > 0 else 1
        amount = amounts[min(day - 1, len(amounts) - 1)]
        return {
            "ok": True,
            "can_claim": can_claim,
            "day": day,
            "amount": amount,
            "streak": bonus_streak,
            "next_in": "24 hours" if not can_claim else "now",
        }


@app.post("/api/app/bonus/claim")
async def app_claim_daily_bonus(request: Request):
    """Claim daily bonus."""
    from bot.database import get_session, Repository
    import datetime
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    if not user_id:
        return {"ok": False, "error": "Missing user_id"}
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        enabled = await repo.get_setting("streak_bonus_enabled", True)
        if not enabled:
            return {"ok": False, "error": "Streak bonus disabled"}
        today = datetime.date.today().isoformat()
        if user.last_bonus_date == today:
            return {"ok": False, "error": "Already claimed today"}
        meta = dict(user.user_meta or {})
        streak = meta.get("bonus_streak", 0) + 1
        amounts = await repo.get_setting("streak_bonus_amounts", [1, 1.5, 2, 2.5, 3, 5, 10])
        day = (streak - 1) % len(amounts) + 1
        amount = amounts[min(day - 1, len(amounts) - 1)]
        await repo.credit_balance(user_id, amount, "daily_bonus", f"Day {day} daily bonus")
        meta["bonus_streak"] = streak
        await repo.update_user_fields(user_id, last_bonus_date=today, user_meta=meta)
        user = await repo.get_user(user_id)
        return {"ok": True, "amount": amount, "day": day, "balance": float(user.balance or 0)}


# ─── In-Memory Game Sessions (Mines / Crash) ────────────────────────────────
_game_sessions: Dict[str, Dict] = {}

def _new_game_id() -> str:
    import secrets, string
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))


BET_MIN = 2
BET_MAX = 50


@app.get("/api/app/game/config")
async def app_game_config():
    """Return game configuration for the Mini App."""
    return {"ok": True, "bet_min": BET_MIN, "bet_max": BET_MAX}


async def _process_game_bet(user_id: int, bet: float, game: str, repo: Repository) -> dict | None:
    """Common validation: check user exists, banned, balance >= bet, etc. Returns error dict or None."""
    user = await repo.get_user(user_id)
    if not user:
        return {"ok": False, "error": "User not found"}
    if user.banned:
        return {"ok": False, "error": "You are banned"}
    if bet < BET_MIN or bet > BET_MAX:
        return {"ok": False, "error": f"Bet must be between ₹{BET_MIN} and ₹{BET_MAX}"}
    balance = float(user.balance or 0)
    if balance < bet:
        return {"ok": False, "error": f"Insufficient balance. Need ₹{bet}"}
    return None


# ─── Dice ────────────────────────────────────────────────────────────────────
@app.post("/api/app/game/dice")
async def app_game_dice(request: Request):
    """Play dice game."""
    from bot.database import get_session, Repository
    from bot.services.risk_engine import RiskEngine
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    bet = data.get("bet")
    if bet is not None:
        bet = float(bet)
    if not user_id or not bet:
        return {"ok": False, "error": "Missing user_id or bet"}
    async with get_session() as session:
        repo = Repository(session)
        err = await _process_game_bet(user_id, bet, "dice", repo)
        if err:
            return err
        await repo.record_game_bet_transaction(user_id, "dice", bet)
        engine = RiskEngine(repo)
        config = await engine.get_game_config("dice")
        profile = await engine.get_profile(user_id)
        game_count = profile.get("total_bets", 0) if profile else 0
        result = await engine.roll_dice(config, game_count, user_id=user_id)
        won = result.get("win", False)
        multiplier = float(result.get("multiplier", 0))
        payout = round(bet * multiplier, 2) if won else 0
        if won and payout > 0:
            await repo.record_game_win_transaction(user_id, "dice", payout, multiplier)
        engine.record_bet("dice", bet, payout)
        await repo.record_game_round(user_id, "dice", bet, payout, multiplier, won,
                                     details={"roll": result.get("roll")})
        engine.update_session(user_id, "dice", bet, won)
        user = await repo.get_user(user_id)
        return {
            "ok": True,
            "roll": result.get("roll"),
            "win": won,
            "multiplier": multiplier,
            "payout": payout,
            "balance": float(user.balance or 0),
        }


# ─── Mines ───────────────────────────────────────────────────────────────────
@app.post("/api/app/game/mines/start")
async def app_game_mines_start(request: Request):
    """Start a new mines game round."""
    from bot.database import get_session, Repository
    from bot.services.risk_engine import RiskEngine
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    bet = data.get("bet")
    if not user_id or not bet:
        return {"ok": False, "error": "Missing user_id or bet"}
    bet = float(bet)
    async with get_session() as session:
        repo = Repository(session)
        err = await _process_game_bet(user_id, bet, "mines", repo)
        if err:
            return err
        engine = RiskEngine(repo)
        config = await engine.get_game_config("mines")
        profile = await engine.get_profile(user_id)
        game_count = profile.get("total_bets", 0) if profile else 0
        profit_level = profile.get("net_profit", 0) if profile else 0
        loss_streak = profile.get("consecutive_losses", 0) if profile else 0
        board_result = await engine.generate_mines(config, mine_count=3, user_game_count=game_count,
                                                     user_id=user_id, profit_level=profit_level,
                                                     loss_streak=loss_streak)
        board = board_result.get("board", ["mine"] * 9)
        mines = board_result.get("mines", 3)
        grid_size = board_result.get("grid_size", 3)
        gid = _new_game_id()
        _game_sessions[gid] = {
            "user_id": user_id,
            "game": "mines",
            "bet": bet,
            "board": board,
            "mines": mines,
            "grid_size": grid_size,
            "revealed": [False] * (grid_size * grid_size),
            "gems_found": 0,
            "active": True,
            "won": False,
            "payout": 0,
        }
        await repo.record_game_bet_transaction(user_id, "mines", bet)
        return {
            "ok": True,
            "game_id": gid,
            "mines": mines,
            "grid_size": grid_size,
        }


@app.post("/api/app/game/mines/reveal")
async def app_game_mines_reveal(request: Request):
    """Reveal a cell in an active mines game."""
    from bot.database import get_session, Repository
    from bot.services.risk_engine import RiskEngine
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    game_id = data.get("game_id")
    cell_index = data.get("cell_index")
    if not user_id or not game_id or cell_index is None:
        return {"ok": False, "error": "Missing parameters"}
    session_state = _game_sessions.get(game_id)
    if not session_state:
        return {"ok": False, "error": "Game not found or expired"}
    if session_state["user_id"] != user_id:
        return {"ok": False, "error": "Not your game"}
    if not session_state["active"]:
        return {"ok": False, "error": "Game already finished"}
    grid_size = session_state["grid_size"]
    total_cells = grid_size * grid_size
    if cell_index < 0 or cell_index >= total_cells:
        return {"ok": False, "error": "Invalid cell"}
    if session_state["revealed"][cell_index]:
        return {"ok": False, "error": "Cell already revealed"}
    session_state["revealed"][cell_index] = True
    is_mine = session_state["board"][cell_index] == "mine"
    async with get_session() as session:
        repo = Repository(session)
        if is_mine:
            session_state["active"] = False
            session_state["won"] = False
            engine = RiskEngine(repo)
            engine.record_bet("mines", session_state["bet"], 0)
            await repo.record_game_round(user_id, "mines", session_state["bet"], 0, 0, False,
                                         details={"gems_found": session_state["gems_found"], "hit_mine": True})
            engine.update_session(user_id, "mines", session_state["bet"], False)
            user = await repo.get_user(user_id)
            return {
                "ok": True,
                "hit": True,
                "gems_found": session_state["gems_found"],
                "multiplier": 0,
                "payout": 0,
                "game_over": True,
                "won": False,
                "balance": float(user.balance or 0),
            }
        else:
            session_state["gems_found"] += 1
            gems = session_state["gems_found"]
            total_mines = session_state["mines"]
            engine = RiskEngine(repo)
            multiplier = engine.get_mines_multiplier(gems, total_mines, grid_size)
            return {
                "ok": True,
                "hit": False,
                "gems_found": gems,
                "multiplier": round(multiplier, 2),
                "payout": round(session_state["bet"] * multiplier, 2),
                "game_over": False,
                "won": False,
            }


@app.post("/api/app/game/mines/cashout")
async def app_game_mines_cashout(request: Request):
    """Cash out from an active mines game."""
    from bot.database import get_session, Repository
    from bot.services.risk_engine import RiskEngine
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    game_id = data.get("game_id")
    if not user_id or not game_id:
        return {"ok": False, "error": "Missing parameters"}
    session_state = _game_sessions.get(game_id)
    if not session_state:
        return {"ok": False, "error": "Game not found or expired"}
    if session_state["user_id"] != user_id:
        return {"ok": False, "error": "Not your game"}
    if not session_state["active"]:
        return {"ok": False, "error": "Game already finished"}
    if session_state["gems_found"] == 0:
        return {"ok": False, "error": "Reveal at least one gem first"}
    gems = session_state["gems_found"]
    total_mines = session_state["mines"]
    grid_size = session_state["grid_size"]
    async with get_session() as session:
        repo = Repository(session)
        engine = RiskEngine(repo)
        multiplier = engine.get_mines_multiplier(gems, total_mines, grid_size)
        payout = round(session_state["bet"] * multiplier, 2)
        session_state["active"] = False
        session_state["won"] = True
        session_state["payout"] = payout
        await repo.record_game_win_transaction(user_id, "mines", payout, multiplier)
        engine.record_bet("mines", session_state["bet"], payout)
        await repo.record_game_round(user_id, "mines", session_state["bet"], payout, multiplier, True,
                                     details={"gems_found": gems, "cashout": True})
        engine.update_session(user_id, "mines", session_state["bet"], True)
        user = await repo.get_user(user_id)
        return {
            "ok": True,
            "gems_found": gems,
            "multiplier": round(multiplier, 2),
            "payout": payout,
            "balance": float(user.balance or 0),
        }



    if user_id and session_state["user_id"] != user_id:
        return {"ok": False, "error": "Not your game"}
    crash_point = session_state["crash_point"]
    if session_state["active"]:
        session_state["active"] = False
        session_state["won"] = False
        async with get_session() as session:
            from bot.database import Repository
            repo = Repository(session)
            engine = RiskEngine(repo)
            engine.record_bet("crash", session_state["bet"], 0)
            await repo.record_game_round(session_state["user_id"], "crash", session_state["bet"], 0, crash_point, False,
                                         details={"crash_point": crash_point, "busted": True})
            engine.update_session(session_state["user_id"], "crash", session_state["bet"], False)
            engine.crash_eng().record_crash(f"crash_{session_state['user_id']}", crash_point)
    return {
        "ok": True,
        "crash_point": crash_point,
        "busted": True,
        "won": False,
    }


# ─── Cleanup stale game sessions ────────────────────────────────────────────
import asyncio as _asyncio

async def _cleanup_stale_games():
    """Periodically remove inactive game sessions older than 5 minutes."""
    while True:
        await _asyncio.sleep(60)
        now = time.time()
        stale = [gid for gid, state in list(_game_sessions.items())
                 if not state.get("active") and state.get("_ts", now) < now - 300]
        for gid in stale:
            _game_sessions.pop(gid, None)
        for state in _game_sessions.values():
            state.setdefault("_ts", now)


@app.on_event("startup")
async def _start_game_cleanup():
    _asyncio.create_task(_cleanup_stale_games())


# ─── Earn / Ads ──────────────────────────────────────────────────────────────
@app.get("/api/app/earn")
async def app_earn(user_id: int):
    """Get earn/ads page data — each ad viewable once per user."""
    import json
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        all_ads = await repo.get_setting("ad_campaigns", [])
        if not isinstance(all_ads, list):
            all_ads = []
        watched_data = await repo.get_setting(f"ad_watched:{user_id}", {})
        if not isinstance(watched_data, dict):
            watched_data = {}
        available_ads = []
        for ad in all_ads:
            if not ad.get("video_url") or ad.get("active") is False:
                continue
            ad_id = str(ad.get("id", ""))
            watched = int(watched_data.get(ad_id, 0))
            if watched >= 1:
                continue
            available_ads.append({
                "id": ad.get("id"),
                "title": ad.get("title", ""),
                "description": ad.get("description", ""),
                "image": ad.get("image", ""),
                "video_url": ad.get("video_url", ""),
                "url": ad.get("url", ""),
                "reward": float(ad.get("reward", 0)),
            })
        return {
            "ok": True,
            "ads": available_ads,
            "count": len(available_ads),
        }


@app.post("/api/app/ad/watch")
async def app_watch_ad(request: Request):
    """Watch an ad and earn — once per user per ad."""
    import json
    from bot.database import get_session, Repository
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    ad_id = data.get("ad_id")
    if not user_id or not ad_id:
        return {"ok": False, "error": "Missing user_id or ad_id"}
    async with get_session() as session:
        repo = Repository(session)
        all_ads = await repo.get_setting("ad_campaigns", [])
        if not isinstance(all_ads, list):
            all_ads = []
        ad = next((a for a in all_ads if a.get("id") == ad_id), None)
        if not ad or not ad.get("video_url") or ad.get("active") is False:
            return {"ok": False, "error": "Ad not available"}
        watched_data = await repo.get_setting(f"ad_watched:{user_id}", {})
        if not isinstance(watched_data, dict):
            watched_data = {}
        ad_id_str = str(ad_id)
        watched = int(watched_data.get(ad_id_str, 0))
        if watched >= 1:
            return {"ok": False, "error": "Already watched this ad"}
        reward = float(ad.get("reward", 0))
        await repo.credit_balance(user_id, reward, "ad_watch", f"Watched ad: {ad.get('title', '')}")
        watched_data[ad_id_str] = 1
        await repo.update_setting(f"ad_watched:{user_id}", json.dumps(watched_data))
        user = await repo.get_user(user_id)
        return {"ok": True, "amount": reward, "balance": float(user.balance or 0)}


@app.get("/api/app/uploads/{filename:path}")
async def app_uploaded_file(filename: str):
    """Serve uploaded files from the uploads directory."""
    import os
    filepath = os.path.normpath(os.path.join(UPLOAD_DIR, filename))
    if not filepath.startswith(UPLOAD_DIR) or not os.path.exists(filepath):
        return Response(status_code=404)
    from fastapi.responses import FileResponse
    return FileResponse(filepath)


@app.get("/api/app/ad-video")
async def app_ad_video(url: str):
    """Proxy ad video — resolves Telegram post links to actual video bytes via Bot API."""
    import httpx, re
    token = settings.BOT_TOKEN
    if not url:
        return Response(status_code=400)
    is_tg = "t.me/" in url or "telegram.me/" in url
    try:
        if is_tg:
            m = re.search(r'(?:t\.me|telegram\.me)/([^/]+)/(\d+)', url)
            if not m:
                return Response(status_code=404)
            channel = m.group(1)
            post_id = int(m.group(2))
            admin_id = 7371674958
            async with httpx.AsyncClient(timeout=20) as client:
                fwd_resp = await client.post(
                    f"https://api.telegram.org/bot{token}/forwardMessage",
                    json={"chat_id": admin_id, "from_chat_id": f"@{channel}", "message_id": post_id}
                )
                fwd_data = fwd_resp.json()
                if not fwd_data.get("ok"):
                    logger.warning("ad-video forwardMessage failed for %s: %s", url, fwd_data.get("description"))
                    return Response(status_code=404)
                msg = fwd_data.get("result", {})
                video = msg.get("video") or msg.get("document") or msg.get("animation")
                if not video:
                    logger.warning("ad-video no video in forwarded message for %s", url)
                    return Response(status_code=404)
                file_id = video.get("file_id")
                if not file_id:
                    return Response(status_code=404)
                file_resp = await client.post(
                    f"https://api.telegram.org/bot{token}/getFile",
                    json={"file_id": file_id}
                )
                file_data = file_resp.json()
                if not file_data.get("ok"):
                    return Response(status_code=404)
                file_path = file_data["result"]["file_path"]
                dl_resp = await client.get(f"https://api.telegram.org/file/bot{token}/{file_path}")
                if dl_resp.status_code != 200:
                    return Response(status_code=404)
                ct = dl_resp.headers.get("content-type", "video/mp4")
                if "video" not in ct and "octet-stream" not in ct:
                    ct = "video/mp4"
                return Response(content=dl_resp.content, media_type=ct,
                                headers={"Cache-Control": "public, max-age=3600"})
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return Response(status_code=404)
            ct = resp.headers.get("content-type", "video/mp4")
            return Response(content=resp.content, media_type=ct,
                            headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        logger.error("ad-video proxy failed: %s", e)
        return Response(status_code=404)


@app.get("/api/app/ad-image/{ad_id}")
async def app_ad_image(ad_id: int):
    """Proxy ad image — resolves ad image URLs to actual image bytes."""
    from bot.database import get_session, Repository
    import httpx, re
    async with get_session() as session:
        repo = Repository(session)
        campaigns = await repo.get_setting("ad_campaigns", [])
        if not isinstance(campaigns, list):
            return Response(status_code=404)
        ad = next((a for a in campaigns if a.get("id") == ad_id), None)
        if not ad or not ad.get("image"):
            return Response(status_code=404)
        image_ref = ad["image"]
    if image_ref.startswith("/api/app/uploads/"):
        from fastapi.responses import FileResponse
        filepath = os.path.normpath(os.path.join(UPLOAD_DIR, os.path.basename(image_ref)))
        if filepath.startswith(UPLOAD_DIR) and os.path.exists(filepath):
            return FileResponse(filepath)
        return Response(status_code=404)
    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(image_ref)
                if resp.status_code != 200:
                    return Response(status_code=404)
                ct = resp.headers.get("content-type", "text/plain").split(";")[0].strip().lower()
                if ct == "text/html":
                    html_text = resp.text
                    image_url = None
                    for pattern in [
                        r'property="og:image"\s+content="([^"]+)"',
                        r'content="([^"]+)"\s+property="og:image"',
                        r"property='og:image'\s+content='([^']+)'",
                        r'content="([^"]+)"\s+property="og:image:url"',
                        r'property="og:image:url"\s+content="([^"]+)"',
                        r'property="twitter:image"\s+content="([^"]+)"',
                        r'<img\s+class="tgme_page_photo_image"\s+src="([^"]+)"',
                    ]:
                        m = re.search(pattern, html_text, re.IGNORECASE)
                        if m:
                            image_url = m.group(1)
                            break
                    if image_url:
                        img_resp = await client.get(image_url)
                        if img_resp.status_code == 200:
                            img_ct = img_resp.headers.get("content-type", "image/jpeg")
                            return Response(content=img_resp.content, media_type=img_ct, headers={"Cache-Control": "public, max-age=3600"})
                    return Response(status_code=404)
                return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "public, max-age=3600"})
        except Exception as e:
            logger.error("ad-image proxy failed for ad %d: %s", ad_id, e)
            return Response(status_code=404)
    token = settings.BOT_TOKEN
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"https://api.telegram.org/bot{token}/getFile", json={"file_id": image_ref})
            d = r.json()
            if not d.get("ok"):
                return Response(status_code=404)
            file_path = d["result"]["file_path"]
            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            resp = await client.get(url)
            if resp.status_code != 200:
                return Response(status_code=404)
            ct = resp.headers.get("content-type", "image/jpeg")
            return Response(content=resp.content, media_type=ct, headers={"Cache-Control": "public, max-age=3600"})
    except Exception:
        return Response(status_code=404)


@app.get("/api/app/task-image/{task_id}")
async def app_task_image(task_id: int):
    """Proxy task image — resolves Telegram file_ids to actual image bytes."""
    from bot.database import get_session, Repository
    import httpx
    async with get_session() as session:
        repo = Repository(session)
        task = await repo.get_task(task_id)
        if not task or not task.image:
            return Response(status_code=404)
        image_ref = task.image
    token = settings.BOT_TOKEN
    if image_ref.startswith("/api/app/uploads/"):
        from fastapi.responses import FileResponse
        filepath = os.path.normpath(os.path.join(UPLOAD_DIR, os.path.basename(image_ref)))
        if filepath.startswith(UPLOAD_DIR) and os.path.exists(filepath):
            return FileResponse(filepath)
        return Response(status_code=404)
    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        import re
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(image_ref)
            if resp.status_code != 200:
                return Response(status_code=404)
            ct = resp.headers.get("content-type", "text/plain").split(";")[0].strip().lower()
            if ct == "text/html":
                html_text = resp.text
                image_url = None
                # Try multiple patterns to extract og:image
                for pattern in [
                    r'property="og:image"\s+content="([^"]+)"',
                    r'content="([^"]+)"\s+property="og:image"',
                    r"property='og:image'\s+content='([^']+)'",
                    r'og:image["\s]+content="([^"]+)"',
                    r'content="([^"]+)"\s+property="og:image:url"',
                    r'property="og:image:url"\s+content="([^"]+)"',
                    r'property="twitter:image"\s+content="([^"]+)"',
                    r'<img\s+class="tgme_page_photo_image"\s+src="([^"]+)"',
                ]:
                    m = re.search(pattern, html_text, re.IGNORECASE)
                    if m:
                        image_url = m.group(1)
                        break
                if image_url:
                    img_resp = await client.get(image_url)
                    if img_resp.status_code == 200:
                        img_ct = img_resp.headers.get("content-type", "image/jpeg")
                        return Response(content=img_resp.content, media_type=img_ct, headers={"Cache-Control": "public, max-age=3600"})
                return Response(status_code=404)
            return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "public, max-age=3600"})
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"https://api.telegram.org/bot{token}/getFile", json={"file_id": image_ref})
            d = r.json()
            if not d.get("ok"):
                return Response(status_code=404)
            file_path = d["result"]["file_path"]
            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            resp = await client.get(url)
            if resp.status_code != 200:
                return Response(status_code=404)
            return Response(content=resp.content, media_type=resp.headers.get("content-type", "image/jpeg"), headers={"Cache-Control": "public, max-age=3600"})
    except Exception:
        return Response(status_code=404)


@app.get("/api/app/image/{key}")
async def app_image(key: str):
    """Proxy withdraw images — resolves Telegram file_ids or URLs to actual image bytes."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        image_ref = await repo.get_image(key)
    logger.info("Image proxy: key=%s image_ref=%s (len=%d)", key, repr(image_ref[:50] if image_ref else ""), len(image_ref) if image_ref else 0)
    if not image_ref:
        logger.warning("Image proxy: no value for key=%s", key)
        return Response(status_code=404)
    import httpx
    import re
    try:
        if image_ref.startswith("/api/app/uploads/"):
            from fastapi.responses import FileResponse
            filepath = os.path.normpath(os.path.join(UPLOAD_DIR, os.path.basename(image_ref)))
            if filepath.startswith(UPLOAD_DIR) and os.path.exists(filepath):
                return FileResponse(filepath)
            return Response(status_code=404)
        if image_ref.startswith("http://") or image_ref.startswith("https://"):
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(image_ref)
                if resp.status_code != 200:
                    logger.warning("Image proxy: URL fetch failed status=%d for key=%s", resp.status_code, key)
                    return Response(status_code=404)
                ct = resp.headers.get("content-type", "text/plain").split(";")[0].strip().lower()
                # If response is HTML (e.g. Telegram post URL), extract image from og:image meta tag
                if ct == "text/html":
                    html_text = resp.text
                    og_match = re.search(r'<meta\s+(?:property="og:image"[^>]*?\s+content="([^"]+)"|content="([^"]+)"[^>]*?\s+property="og:image")', html_text, re.IGNORECASE)
                    if not og_match:
                        og_match = re.search(r"<meta\s+(?:property='og:image'[^>]*?\s+content='([^']+)'|content='([^']+)'[^>]*?\s+property='og:image')", html_text, re.IGNORECASE)
                    if og_match:
                        image_url = og_match.group(1) or og_match.group(2)
                        logger.info("Image proxy: extracted og:image for key=%s: %s", key, image_url)
                        img_resp = await client.get(image_url)
                        if img_resp.status_code == 200:
                            img_ct = img_resp.headers.get("content-type", "image/jpeg")
                            return Response(
                                content=img_resp.content,
                                media_type=img_ct,
                                headers={"Cache-Control": "public, max-age=3600"}
                            )
                    logger.warning("Image proxy: no og:image found in HTML for key=%s", key)
                    return Response(status_code=404)
                ct = resp.headers.get("content-type", "image/jpeg")
                logger.info("Image proxy: URL success key=%s ct=%s size=%d", key, ct, len(resp.content))
                return Response(
                    content=resp.content,
                    media_type=ct,
                    headers={"Cache-Control": "public, max-age=3600"}
                )
        token = settings.BOT_TOKEN
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/getFile",
                json={"file_id": image_ref}
            )
            d = r.json()
            if not d.get("ok"):
                logger.error("Image proxy: getFile failed for key=%s response=%s", key, d)
                return Response(status_code=404)
            file_path = d["result"]["file_path"]
            url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning("Image proxy: file download failed status=%d for key=%s", resp.status_code, key)
                return Response(status_code=404)
            ct = resp.headers.get("content-type", "image/jpeg")
            logger.info("Image proxy: file_id success key=%s ct=%s size=%d", key, ct, len(resp.content))
            return Response(
                content=resp.content,
                media_type=ct,
                headers={"Cache-Control": "public, max-age=3600"}
            )
    except Exception as e:
        logger.error("Image proxy: exception for key=%s: %s", key, e)
        return Response(status_code=404)


@app.get("/api/app/wallet")
async def app_wallet(user_id: int):
    """Get wallet information."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        meta = user.user_meta or {}
        return {
            "ok": True,
            "wallet": {
                "balance": float(user.balance or 0),
                "pending": 0,
                "withdrawn": float(meta.get("total_withdrawn", 0)),
                "upi": meta.get("upi", ""),
            },
            "transactions": await repo.get_user_transactions(user_id, 20),
            "min_withdraw": float(await repo.get_setting("min_withdraw", 10)),
            "min_star_withdraw": int(await repo.get_setting("min_star_withdraw", 15)),
            "img_withdraw_upi": str(await repo.get_setting("img_withdraw_upi", "")),
            "img_withdraw_stars": str(await repo.get_setting("img_withdraw_stars", "")),
            "img_withdraw_redeem": str(await repo.get_setting("img_withdraw_redeem", "")),
        }


@app.get("/api/app/redeem-codes")
async def app_redeem_codes(user_id: int):
    """Get user's redeemed codes history."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        codes = await repo.get_user_redeem_codes(user_id, 50)
        return {"ok": True, "codes": codes}


@app.post("/api/app/withdraw")
async def app_withdraw(request: Request):
    """Request withdrawal from Mini App. Redeem codes are instant."""
    from bot.database import get_session, Repository
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    method = data.get("method", "upi")
    amount = float(data.get("amount", 0))
    upi = data.get("upi", "")
    stars = int(data.get("stars", 0))
    post_link = data.get("post_link", "")
    if not user_id or amount <= 0:
        return {"ok": False, "error": "Invalid request"}
    async with get_session() as session:
        repo_for_settings = Repository(session)
        min_star_withdraw = int(await repo_for_settings.get_setting("min_star_withdraw", 15))
        max_star_withdraw = int(await repo_for_settings.get_setting("max_star_withdraw", 500))
    if method == "stars":
        if stars < min_star_withdraw:
            return {"ok": False, "error": f"Minimum {min_star_withdraw}⭐ for stars withdrawal"}
        if stars > max_star_withdraw:
            return {"ok": False, "error": f"Maximum {max_star_withdraw}⭐ for stars withdrawal"}
    else:
        min_amt = {"upi": float(await repo_for_settings.get_setting("min_withdraw", 10)), "redeem": 10}
        max_amt = {"upi": float(await repo_for_settings.get_setting("max_withdraw", 10000)), "redeem": 500}
        if amount < min_amt.get(method, 10):
            return {"ok": False, "error": f"Minimum ₹{min_amt.get(method, 10)} for {method}"}
        if amount > max_amt.get(method, 10000):
            return {"ok": False, "error": f"Maximum ₹{max_amt.get(method, 10000)} for {method}"}
        if method == "upi":
            if await repo_for_settings.has_pending_withdrawal(user_id):
                return {"ok": False, "error": "You already have a pending withdrawal. Wait for it to be processed."}
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        if (user.balance or 0) < amount:
            return {"ok": False, "error": "Insufficient balance"}
        # Daily limit check
        daily_limit = await repo.get_setting("daily_withdraw_limit", 3)
        if daily_limit > 0:
            today_count = await repo.count_today_withdrawals(user_id)
            if today_count >= daily_limit:
                return {"ok": False, "error": f"Daily withdrawal limit reached ({daily_limit}/day)"}
        # Pending withdrawal check
        if method == "redeem":
            pending = await repo.get_setting(f"pending_redeem:{user_id}")
            if pending:
                return {"ok": False, "error": "You already have a pending redeem request"}
            # Check redeem stock enabled
            redeem_enabled = await repo.get_setting("redeem_stock_enabled", True)
            if not redeem_enabled:
                return {"ok": False, "error": "Redeem codes are currently disabled"}
            # Instant redeem
            code = await repo.get_available_redeem_code(amount, user_id)
            if not code:
                return {"ok": False, "error": f"No ₹{amount:.0f} codes available. Try a different amount."}
            await repo.debit_balance(user_id, amount, "redeem_withdrawal", f"Redeem code: ₹{amount}")
            w_req = await repo.add_withdrawal(user_id, amount, method="redeem")
            await repo.update_withdrawal_redeem_code(w_req.id, code)
            await repo.update_withdrawal_status(w_req.id, "paid")
            meta = dict(user.user_meta or {})
            meta["total_withdrawn"] = meta.get("total_withdrawn", 0) + amount
            await repo.update_user_fields(user_id, user_meta=meta)
            user = await repo.get_user(user_id)
            return {"ok": True, "balance": float(user.balance or 0), "code": code, "withdrawal_id": w_req.id, "message": "Redeem code issued!"}
        # UPI / Stars — standard pending withdrawal
        await repo.debit_balance(user_id, amount, f"withdraw_{method}", f"Withdrawal via {method}")
        meta = dict(user.user_meta or {})
        if method == "upi" and upi:
            meta["upi"] = upi
        meta["total_withdrawn"] = meta.get("total_withdrawn", 0) + amount
        await repo.update_user_fields(user_id, user_meta=meta)
        channel_link = post_link if method == "stars" else ""
        await repo.add_withdrawal(user_id, amount, method=method, upi_id=upi if method == "upi" else None,
                                  stars=stars, channel_link=channel_link)
        user = await repo.get_user(user_id)
        return {"ok": True, "balance": float(user.balance or 0), "message": "Withdrawal requested"}


@app.get("/api/app/refer")
async def app_refer(user_id: int):
    """Get referral information."""
    import random
    import string
    from bot.database import get_session, Repository
    from sqlalchemy import select
    from bot.database.models_sql import UserTable
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        meta = dict(user.user_meta or {})
        code = meta.get("referral_code", "")
        if not code:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            meta["referral_code"] = code
            await repo.update_user_fields(user_id, user_meta=meta)
        referral_ids = user.referrals or []
        ref_list = []
        total_active = 0
        total_earned = 0
        for rid in referral_ids[:10]:
            r = await repo.get_user(rid)
            if r:
                is_active = not r.banned
                if is_active:
                    total_active += 1
                earned = float(getattr(r, 'referral_earnings', 0) or 0)
                total_earned += earned
                ref_list.append({
                    "id": r.user_id,
                    "name": r.first_name or "User",
                    "date": str(getattr(r, 'joined_at', ''))[:10] if hasattr(r, 'joined_at') else "",
                    "earned": earned,
                    "active": is_active,
                })
        per_refer_reward = float(await repo.get_setting("fixed_referral_reward", 0.5))
        referral_paused = await repo.get_setting("refer_paused", False)
        return {
            "ok": True,
            "bot_username": settings.BOT_USERNAME,
            "per_refer_reward": per_refer_reward,
            "referral_paused": bool(referral_paused),
            "referral": {
                "code": code,
                "total": len(referral_ids),
                "active": total_active,
                "earned": float(user.referral_earnings or 0),
                "referrals": ref_list,
            }
        }


@app.get("/api/app/promoted")
async def app_promoted(user_id: int = 0):
    """Get promoted items."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        items = await repo.get_setting("promoted_items", [])
        if not isinstance(items, list):
            items = []
        return {"ok": True, "items": items}


@app.get("/api/app/promo-config")
async def app_promo_config(user_id: int = 0):
    """Get promo price and QR for users."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        price = await repo.get_setting("promo_price", 50)
        qr = await repo.get_setting("promo_qr_image", "")
        desc = await repo.get_setting("promo_description", "One-time payment for featured promotion")
    proxy_url = ""
    if qr:
        proxy_url = "https://taskhub-app-ten.vercel.app/api/app/image/promo_qr_image"
    return {"ok": True, "promo_price": float(price), "promo_qr_image": qr, "promo_qr_proxy_url": proxy_url, "promo_description": desc}


@app.post("/api/app/promote/submit")
async def app_submit_promotion(request: Request):
    """User submits a promotion request."""
    from bot.database import get_session, Repository
    from datetime import datetime
    try:
        try:
            data = await request.json()
        except Exception:
            return {"ok": False, "error": "Invalid JSON"}
        user_id = data.get("user_id")
        sub_type = data.get("type", "promoted")
        title = data.get("title", "")
        description = data.get("description", "")
        details = data.get("details", "")
        url = data.get("url", "")
        image = data.get("image", "")
        color = data.get("color", "#7b5ef8")
        try:
            reward = float(data.get("reward", 0))
        except (ValueError, TypeError):
            reward = 0.0
        payment_proof = (data.get("payment_proof", "") or "")[:500000]
        transaction_id = data.get("transaction_id", "")
        if not user_id:
            return {"ok": False, "error": "Missing user_id"}
        if not title:
            return {"ok": False, "error": "Title is required"}
        async with get_session() as session:
            repo = Repository(session)
            submissions = await repo.get_setting("pending_user_submissions", [])
            if not isinstance(submissions, list):
                submissions = []
            new_id = max([s.get("id", 0) for s in submissions], default=0) + 1
            submissions.append({
                "id": new_id,
                "user_id": user_id,
                "type": sub_type,
                "title": title,
                "description": description,
                "details": details,
                "url": url,
                "image": image,
                "color": color,
                "reward": reward,
                "payment_proof": payment_proof,
                "transaction_id": transaction_id,
                "status": "pending",
                "date": datetime.now().isoformat(),
            })
            await repo.update_setting("pending_user_submissions", submissions)
        return {"ok": True, "message": "Submission received! Admin will review it.", "id": new_id}
    except Exception as exc:
        logger.exception("Promote submit failed: %s", exc)
        return {"ok": False, "error": "Server error. Please try again."}


@app.get("/api/app/leaderboard")
async def app_leaderboard(user_id: int = 0):
    """Get top earners leaderboard."""
    from bot.database import get_session, Repository
    from bot.database.models_sql import UserTable
    from sqlalchemy import select, desc
    async with get_session() as session:
        repo = Repository(session)
        result = await session.execute(
            select(UserTable)
            .where(UserTable.banned == False)
            .where(UserTable.lifetime_earnings > 0)
            .order_by(desc(UserTable.lifetime_earnings))
            .limit(20)
        )
        top_users = result.scalars().all()
        leaders = []
        for i, u in enumerate(top_users):
            meta = dict(u.user_meta or {})
            pfp = ""
            cached_pfp = meta.get("pfp_url", "")
            cached_at = meta.get("pfp_cached_at", 0)
            cache_age = time.time() - cached_at if cached_at else float('inf')
            if cached_pfp and cache_age < 1800:
                pfp = f"/api/user/{u.user_id}/pfp"
            else:
                try:
                    file_path = await _get_tg_file_path(u.user_id)
                    if file_path:
                        meta["pfp_url"] = file_path
                        meta["pfp_cached_at"] = time.time()
                        try:
                            await repo.update_user_fields(u.user_id, user_meta=meta)
                        except Exception:
                            pass
                        pfp = f"/api/user/{u.user_id}/pfp"
                except Exception:
                    pass
            leaders.append({
                "rank": i + 1,
                "name": u.first_name or "User",
                "user_id": u.user_id,
                "pfp": pfp,
                "earnings": float(u.lifetime_earnings or 0),
                "tasks": len(u.completed_tasks or []),
            })
        my_rank = "-"
        my_earnings = 0.0
        if user_id:
            me = await repo.get_user(user_id)
            if me:
                my_earnings = float(me.lifetime_earnings or 0)
                rank_result = await session.execute(
                    select(UserTable)
                    .where(UserTable.banned == False)
                    .where(UserTable.lifetime_earnings > my_earnings)
                )
                my_rank = len(rank_result.scalars().all()) + 1
        return {"ok": True, "leaders": leaders, "my_rank": my_rank, "my_earnings": my_earnings}


if __name__ == "__main__":
    # Start ASGI server
    uvicorn.run(
        "bot.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=not settings.is_production
    )

