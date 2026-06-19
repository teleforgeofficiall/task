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
                        sid = int(startapp)
                        if sid != user_id:
                            ref_user = await repo.get_user(sid)
                            if ref_user and not ref_user.banned:
                                referrer_id = sid
                    except (ValueError, TypeError):
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
            result = []
            for t in tasks:
                result.append({
                    "id": t.id,
                    "title": t.description[:50] if isinstance(t.description, str) else "Task",
                    "description": t.description or "",
                    "reward": float(t.reward),
                    "type": t.task_type or "manual",
                    "icon": "📋",
                    "image": t.image or "",
                    "color": t.color or "#7b5ef8",
                    "color2": t.color2 or "#5a3fd6",
                    "duration": t.duration_text or "15 min",
                    "completions": t.completion_count or 0,
                    "is_completed": t.id in completed_tasks,
                    "guide": t.guide or "",
                    "channel_title": t.channel_title or "",
                    "video_url": t.video_url or "",
                    "steps": t.steps or [],
                    "is_multi_reward": t.is_multi_reward or False,
                    "offer_url": t.offer_url or "",
                    "referrer_reward": float(t.referrer_reward or 0),
                    "completer_reward": float(t.completer_reward or 0),
                    "max_completers": t.max_completers or 0,
                    "current_completers": t.current_completers or 0,
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
                "title": t.description[:50] if isinstance(t.description, str) else "Task",
                "description": t.description or "",
                "reward": float(t.reward),
                "type": t.task_type or "manual",
                "icon": "📋",
                "image": t.image or "",
                "color": t.color or "#7b5ef8",
                "color2": t.color2 or "#5a3fd6",
                "duration": t.duration_text or "15 min",
                "completions": t.completion_count or 0,
                "is_completed": t.id in completed_tasks,
                "guide": t.guide or "",
                "channel_title": t.channel_title or "",
                "video_url": t.video_url or "",
                "steps": t.steps or [],
                "is_multi_reward": t.is_multi_reward or False,
                "offer_url": t.offer_url or "",
                "ref_enabled": True,
                "ref_code": f"T{user_id}T{task_id}",
                "ref_link": f"https://t.me/{settings.BOT_USERNAME}?start=ref_{user_id}_task_{task_id}",
                "referrer_reward": float(t.referrer_reward or 0),
                "completer_reward": float(t.completer_reward or 0),
                "max_completers": t.max_completers or 0,
                "current_completers": t.current_completers or 0,
            }
        }


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
    proof_image = (proof_image or "")[:500000]
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
            await repo.add_proof(user_id, task_id, proof_image, "photo")
        except Exception as exc:
            logger.exception("add_proof failed for user %s task %s: %s", user_id, task_id, exc)
            return {"ok": False, "error": "Failed to save proof. Try a smaller image."}
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


@app.post("/api/app/spin")
async def app_spin(request: Request):
    """Spin & Win."""
    import random
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
        enabled = await repo.get_setting("spin_enabled", True)
        if not enabled:
            return {"ok": False, "error": "Spin disabled"}
        meta = dict(user.user_meta or {})
        cooldown_hours = int(await repo.get_setting("spin_cooldown_hours", 24))
        price = float(await repo.get_setting("spin_price", 0.0))
        segments = await repo.get_setting("spin_segments", [0.5, 1, 2, 3, 5, 0, 1.5, 0.75])
        last_spin = meta.get("last_spin_date", "")
        today = datetime.date.today().isoformat()
        if cooldown_hours >= 24:
            if last_spin == today:
                return {"ok": False, "error": "Already spun today"}
        else:
            last_spin_dt = meta.get("last_spin_datetime", "")
            if last_spin_dt:
                try:
                    elapsed = (datetime.datetime.now() - datetime.datetime.fromisoformat(last_spin_dt)).total_seconds()
                    if elapsed < cooldown_hours * 3600:
                        remaining = int(cooldown_hours * 3600 - elapsed)
                        return {"ok": False, "error": f"Wait {remaining // 60}m {remaining % 60}s"}
                except Exception:
                    pass
        if price > 0:
            balance = float(user.balance or 0)
            if balance < price:
                return {"ok": False, "error": f"Insufficient balance. Need ₹{price:.2f}"}
            await repo.debit_balance(user_id, price, "spin_fee", f"Spin fee: ₹{price:.2f}")
        amount = random.choice(segments)
        if amount > 0:
            await repo.credit_balance(user_id, amount, "spin_win", f"Spin & Win: ₹{amount}")
        meta["last_spin_date"] = today
        meta["last_spin_datetime"] = datetime.datetime.now().isoformat()
        await repo.update_user_fields(user_id, user_meta=meta)
        user = await repo.get_user(user_id)
        return {"ok": True, "amount": amount, "balance": float(user.balance or 0)}


@app.get("/api/app/spin-config")
async def app_spin_config(user_id: int = 0):
    """Get spin wheel configuration for the Mini App."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        enabled = await repo.get_setting("spin_enabled", True)
        segments = await repo.get_setting("spin_segments", [0.5, 1, 2, 3, 5, 0, 1.5, 0.75])
        price = float(await repo.get_setting("spin_price", 0.0))
        cooldown_hours = int(await repo.get_setting("spin_cooldown_hours", 24))
    return {"ok": True, "enabled": enabled, "segments": segments, "price": price, "cooldown_hours": cooldown_hours}


# ─── In-Memory Game Sessions (Mines / Crash) ────────────────────────────────
_game_sessions: Dict[str, Dict] = {}

def _new_game_id() -> str:
    import secrets, string
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))


BET_AMOUNTS = [5, 10, 25, 50, 100]


@app.get("/api/app/game/config")
async def app_game_config():
    """Return game configuration for the Mini App."""
    return {"ok": True, "bet_amounts": BET_AMOUNTS}


async def _process_game_bet(user_id: int, bet: float, game: str, repo: Repository) -> dict | None:
    """Common validation: check user exists, banned, balance >= bet, etc. Returns error dict or None."""
    user = await repo.get_user(user_id)
    if not user:
        return {"ok": False, "error": "User not found"}
    if user.banned:
        return {"ok": False, "error": "You are banned"}
    if bet not in BET_AMOUNTS:
        return {"ok": False, "error": "Invalid bet amount"}
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


# ─── Slots ───────────────────────────────────────────────────────────────────
@app.post("/api/app/game/slots")
async def app_game_slots(request: Request):
    """Play slots game."""
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
        err = await _process_game_bet(user_id, bet, "slots", repo)
        if err:
            return err
        await repo.record_game_bet_transaction(user_id, "slots", bet)
        engine = RiskEngine(repo)
        config = await engine.get_game_config("slots")
        profile = await engine.get_profile(user_id)
        game_count = profile.get("total_bets", 0) if profile else 0
        result = await engine.spin_slots(config, game_count, user_id=user_id)
        won = result.get("win", False)
        multiplier = float(result.get("multiplier", 0))
        payout = round(bet * multiplier, 2) if won else 0
        if won and payout > 0:
            await repo.record_game_win_transaction(user_id, "slots", payout, multiplier)
        engine.record_bet("slots", bet, payout)
        await repo.record_game_round(user_id, "slots", bet, payout, multiplier, won,
                                     details={"reels": result.get("reels"), "jackpot": result.get("jackpot", False)})
        engine.update_session(user_id, "slots", bet, won)
        user = await repo.get_user(user_id)
        return {
            "ok": True,
            "reels": result.get("reels"),
            "win": won,
            "multiplier": multiplier,
            "payout": payout,
            "jackpot": result.get("jackpot", False),
            "near_miss": result.get("near_miss", False),
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


# ─── Crash ───────────────────────────────────────────────────────────────────
@app.post("/api/app/game/crash/start")
async def app_game_crash_start(request: Request):
    """Start a new crash game round."""
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
        err = await _process_game_bet(user_id, bet, "crash", repo)
        if err:
            return err
        engine = RiskEngine(repo)
        config = await engine.get_game_config("crash")
        profile = await engine.get_profile(user_id)
        game_count = profile.get("total_bets", 0) if profile else 0
        crash_point = await engine.generate_crash_point(config, game_count, user_id=user_id)
        gid = _new_game_id()
        _game_sessions[gid] = {
            "user_id": user_id,
            "game": "crash",
            "bet": bet,
            "crash_point": crash_point,
            "cashout_mult": 0,
            "active": True,
            "won": False,
            "payout": 0,
        }
        await repo.record_game_bet_transaction(user_id, "crash", bet)
        return {
            "ok": True,
            "game_id": gid,
        }


@app.post("/api/app/game/crash/cashout")
async def app_game_crash_cashout(request: Request):
    """Cash out before crash."""
    from bot.database import get_session, Repository
    from bot.services.risk_engine import RiskEngine
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    user_id = data.get("user_id")
    game_id = data.get("game_id")
    cashout_mult = data.get("cashout_mult")
    if not user_id or not game_id or not cashout_mult:
        return {"ok": False, "error": "Missing parameters"}
    cashout_mult = float(cashout_mult)
    session_state = _game_sessions.get(game_id)
    if not session_state:
        return {"ok": False, "error": "Game not found or expired"}
    if session_state["user_id"] != user_id:
        return {"ok": False, "error": "Not your game"}
    if not session_state["active"]:
        return {"ok": False, "error": "Game already finished"}
    crash_point = session_state["crash_point"]
    if cashout_mult >= crash_point:
        return {"ok": False, "error": "Already crashed", "crash_point": crash_point}
    if cashout_mult < 1.0:
        return {"ok": False, "error": "Invalid cashout multiplier"}
    payout = round(session_state["bet"] * cashout_mult, 2)
    session_state["active"] = False
    session_state["won"] = True
    session_state["payout"] = payout
    session_state["cashout_mult"] = cashout_mult
    async with get_session() as session:
        repo = Repository(session)
        engine = RiskEngine(repo)
        await repo.record_game_win_transaction(user_id, "crash", payout, cashout_mult)
        engine.record_bet("crash", session_state["bet"], payout)
        await repo.record_game_round(user_id, "crash", session_state["bet"], payout, cashout_mult, True,
                                     details={"crash_point": crash_point})
        engine.update_session(user_id, "crash", session_state["bet"], True)
        engine.crash_eng().record_crash(f"crash_{user_id}", crash_point)
        user = await repo.get_user(user_id)
        return {
            "ok": True,
            "cashout_mult": cashout_mult,
            "crash_point": crash_point,
            "payout": payout,
            "balance": float(user.balance or 0),
        }


@app.post("/api/app/game/crash/result")
async def app_game_crash_result(request: Request):
    """Get crash result (after crash)."""
    try:
        data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}
    game_id = data.get("game_id")
    user_id = data.get("user_id")
    if not game_id:
        return {"ok": False, "error": "Missing game_id"}
    session_state = _game_sessions.get(game_id)
    if not session_state:
        return {"ok": False, "error": "Game not found or expired"}
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
    """Get earn/ads page data."""
    import json
    from datetime import date, datetime, timedelta
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        ads = await repo.get_setting("ad_campaigns", [])
        ad_goal_target = int(await repo.get_setting("ad_goal_target", 20))
        ad_goal_reward = float(await repo.get_setting("ad_goal_reward", 1))
        goal_data = await repo.get_setting(f"ad_goal:{user_id}", {})
        if not isinstance(goal_data, dict):
            goal_data = {}
        today = str(date.today())
        goal_date = goal_data.get("date", "")
        goal_count = int(goal_data.get("count", 0))
        if goal_date != today:
            goal_count = 0
            goal_data = {"date": today, "count": 0}
            await repo.update_setting(f"ad_goal:{user_id}", json.dumps(goal_data))
        capped = min(goal_count, ad_goal_target)
        now = datetime.now()
        reset_at = datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)
        reset_seconds = int((reset_at - now).total_seconds())
        reset_hrs = max(0, reset_seconds // 3600)
        reset_min = max(0, (reset_seconds % 3600) // 60)
        reset_str = f"{reset_hrs}h {reset_min}m" if reset_hrs > 0 else f"{reset_min}m"
        return {
            "ok": True,
            "ads": ads if isinstance(ads, list) else [],
            "has_ads": len(ads) > 0,
            "ad_goal": {
                "current": capped,
                "target": ad_goal_target,
                "reward": ad_goal_reward,
                "reset_in": reset_str,
                "completed": goal_count >= ad_goal_target,
                "no_ads": len(ads) == 0,
            }
        }


@app.post("/api/app/ad/watch")
async def app_watch_ad(request: Request):
    """Watch an ad and earn."""
    import json
    from datetime import date, datetime, timedelta
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
        ad_goal_target = int(await repo.get_setting("ad_goal_target", 20))
        ad_goal_reward = float(await repo.get_setting("ad_goal_reward", 1))
        goal_data = await repo.get_setting(f"ad_goal:{user_id}", {})
        if not isinstance(goal_data, dict):
            goal_data = {}
        today = str(date.today())
        goal_date = goal_data.get("date", "")
        goal_count = int(goal_data.get("count", 0))
        if goal_date != today:
            goal_count = 0
            goal_data = {"date": today, "count": 0}
        if goal_count >= ad_goal_target:
            user = await repo.get_user(user_id)
            now = datetime.now()
            reset_at = datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)
            reset_seconds = int((reset_at - now).total_seconds())
            reset_hrs = max(0, reset_seconds // 3600)
            reset_min = max(0, (reset_seconds % 3600) // 60)
            reset_str = f"{reset_hrs}h {reset_min}m" if reset_hrs > 0 else f"{reset_min}m"
            return {"ok": True, "amount": 0, "balance": float(user.balance or 0),
                    "completed": True, "message": f"Target complete! Come back in {reset_str}"}
        ads = await repo.get_setting("ad_campaigns", [])
        if not isinstance(ads, list) or len(ads) == 0:
            return {"ok": False, "error": "No ads available"}
        per_ad = round(ad_goal_reward / ad_goal_target, 4) if ad_goal_target > 0 else 0.05
        await repo.credit_balance(user_id, per_ad, "ad_watch", "Watched ad")
        goal_count += 1
        goal_data["count"] = goal_count
        await repo.update_setting(f"ad_goal:{user_id}", json.dumps(goal_data))
        user = await repo.get_user(user_id)
        completed = goal_count >= ad_goal_target
        return {"ok": True, "amount": per_ad, "balance": float(user.balance or 0), "completed": completed}


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
    if not user_id or amount <= 0:
        return {"ok": False, "error": "Invalid request"}
    min_amt = {"upi": 10, "stars": 5, "redeem": 10}
    max_amt = {"upi": 10000, "stars": 500, "redeem": 500}
    if amount < min_amt.get(method, 10):
        return {"ok": False, "error": f"Minimum ₹{min_amt.get(method, 10)} for {method}"}
    if amount > max_amt.get(method, 10000):
        return {"ok": False, "error": f"Maximum ₹{max_amt.get(method, 10000)} for {method}"}
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
        await repo.add_withdrawal(user_id, amount, method=method, upi_id=upi if method == "upi" else None)
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
        return {
            "ok": True,
            "bot_username": settings.BOT_USERNAME,
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
    return {"ok": True, "promo_price": float(price), "promo_qr_image": qr}


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
        reward = float(data.get("reward", 0))
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

