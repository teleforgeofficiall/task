"""
main.py — Application entry point.
Bootstraps python-telegram-bot and FastAPI into a unified event loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
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
        pfp_url = photos.photos[0][-1].file_id if photos.photos else ""
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


@app.get("/api/user/{user_id}/photo")
async def api_user_photo(user_id: int):
    """Return downloadable URL for user's profile photo."""
    try:
        photos = await ptb_app.bot.get_user_profile_photos(user_id, limit=1)
        if not photos.photos:
            return {"ok": False, "error": "No photo"}
        file_id = photos.photos[0][-1].file_id
        file = await ptb_app.bot.get_file(file_id)
        return {"ok": True, "url": file.file_path}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/verify/{user_id}")
async def verify_page(user_id: int):
    """Serve the device verification HTML page with bot username injected."""
    import os
    bot_username = ""
    try:
        bot_user = await ptb_app.bot.get_me()
        bot_username = bot_user.username or ""
    except Exception:
        pass
    html_path = os.path.join(os.path.dirname(__file__), "..", "vercel", "verify.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = "<html><body><h2>Verification page not found</h2></body></html>"
    html = html.replace("__BOT_USERNAME__", bot_username)
    return Response(content=html, media_type="text/html")


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
async def app_init(user_id: int, init_data: str = "", hash: str = ""):
    """Initialize the Mini App - check user, channels, welcome bonus."""
    try:
        from bot.database import get_session, Repository
        from bot.middlewares.auth import get_unjoined_channels
        async with get_session() as session:
            repo = Repository(session)
            user = await repo.get_user(user_id)
            if not user:
                user = await repo.create_user(user_id, "User", "User")
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
            welcome_bonus_claimed = user.referral_earnings is not None or (await repo.get_setting("welcome_bonus_claimed_" + str(user_id), False))
            if not welcome_bonus_claimed:
                welcome_bonus_claimed = False
            try:
                pfp = ""
                if not settings.DISABLE_TELEGRAM_NETWORK:
                    photos = await ptb_app.bot.get_user_profile_photos(user_id, limit=1)
                    if photos.photos:
                        f = await ptb_app.bot.get_file(photos.photos[0][-1].file_id)
                        pfp = f.file_path or ""
            except Exception as exc:
                logger.debug("app_init: profile photo failed: %s", exc)
                pfp = ""
            return {
                "ok": True,
                "user": {
                    "id": user.user_id,
                    "first_name": user.first_name,
                    "username": user.username,
                    "balance": float(user.balance or 0),
                    "pfp": pfp,
                    "upi": "",
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
        await repo.credit_balance(user_id, amount, "welcome_bonus", "Welcome bonus via Mini App")
        await repo.update_setting("welcome_bonus_claimed_" + str(user_id), True)
        return {"ok": True, "amount": amount}


@app.get("/api/app/tasks")
async def app_tasks(user_id: int):
    """Get all available tasks for the Mini App."""
    from bot.database import get_session, Repository
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
                "color": "#7b5ef8",
                "color2": "#5a3fd6",
                "duration": "15 min",
                "completions": t.completion_count or 0,
                "is_completed": t.id in completed_tasks,
                "guide": t.guide or "",
                "image": t.image or "",
                "channel_title": t.channel_title or "",
            })
        return {"ok": True, "tasks": result}


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
                "color": "#7b5ef8",
                "color2": "#5a3fd6",
                "duration": "15 min",
                "completions": t.completion_count or 0,
                "is_completed": t.id in completed_tasks,
                "guide": t.guide or "",
                "image": t.image or "",
                "channel_title": t.channel_title or "",
            }
        }


@app.post("/api/app/task/{task_id}/submit")
async def app_submit_proof(task_id: int, request: Request):
    """Submit task proof from Mini App."""
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
        await repo.add_proof(user_id, task_id, proof_image, "photo")
        completed_tasks.append(task_id)
        await repo.update_user_fields(user_id, completed_tasks=completed_tasks)
        await repo.increment_task_completion(task_id)
        return {"ok": True, "message": "Proof submitted for review"}


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
        last_bonus = user.last_bonus_date
        today = datetime.date.today().isoformat()
        can_claim = last_bonus != today
        meta = user.user_meta or {}
        bonus_streak = meta.get("bonus_streak", 0)
        if can_claim:
            day = (bonus_streak % 7) + 1
        else:
            day = ((bonus_streak - 1) % 7) + 1 if bonus_streak > 0 else 1
        amounts = [1, 1.5, 2, 2.5, 3, 5, 10]
        amount = amounts[min(day - 1, 6)]
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
        today = datetime.date.today().isoformat()
        if user.last_bonus_date == today:
            return {"ok": False, "error": "Already claimed today"}
        meta = dict(user.user_meta or {})
        streak = meta.get("bonus_streak", 0) + 1
        day = (streak - 1) % 7 + 1
        amounts = [1, 1.5, 2, 2.5, 3, 5, 10]
        amount = amounts[min(day - 1, 6)]
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
        meta = dict(user.user_meta or {})
        last_spin = meta.get("last_spin_date", "")
        today = datetime.date.today().isoformat()
        if last_spin == today:
            return {"ok": False, "error": "Already spun today"}
        segments = [0.5, 1, 2, 3, 5, 0, 1.5, 0.75]
        amount = random.choice(segments)
        await repo.credit_balance(user_id, amount, "spin_win", f"Spin & Win: ₹{amount}")
        meta["last_spin_date"] = today
        await repo.update_user_fields(user_id, user_meta=meta)
        user = await repo.get_user(user_id)
        return {"ok": True, "amount": amount, "balance": float(user.balance or 0)}


@app.get("/api/app/earn")
async def app_earn(user_id: int):
    """Get earn/ads page data."""
    from bot.database import get_session, Repository
    async with get_session() as session:
        repo = Repository(session)
        ads = await repo.get_setting("ad_campaigns", [])
        ad_goal_current = await repo.get_setting(f"ad_goal:{user_id}", 0)
        ad_goal_target = await repo.get_setting("ad_goal_target", 20)
        ad_goal_reward = await repo.get_setting("ad_goal_reward", 1)
        return {
            "ok": True,
            "ads": ads if isinstance(ads, list) else [],
            "ad_goal": {
                "current": int(ad_goal_current),
                "target": int(ad_goal_target),
                "reward": float(ad_goal_reward),
                "reset_in": "24h",
            }
        }


@app.post("/api/app/ad/watch")
async def app_watch_ad(request: Request):
    """Watch an ad and earn."""
    import random
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
        amount = round(random.uniform(0.05, 0.15), 2)
        await repo.credit_balance(user_id, amount, "ad_watch", "Watched ad")
        ad_count = int(await repo.get_setting(f"ad_goal:{user_id}", 0))
        await repo.update_setting(f"ad_goal:{user_id}", ad_count + 1)
        user = await repo.get_user(user_id)
        return {"ok": True, "amount": amount, "balance": float(user.balance or 0)}


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
            "transactions": [],
            "min_withdraw": float(await repo.get_setting("min_withdraw_upi", 10)),
        }


@app.post("/api/app/withdraw")
async def app_withdraw(request: Request):
    """Request withdrawal from Mini App."""
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
    min_amt = {"upi": 10, "stars": 5, "redeem": 50}
    if amount < min_amt.get(method, 10):
        return {"ok": False, "error": f"Minimum ₹{min_amt.get(method, 10)} for {method}"}
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(user_id)
        if not user:
            return {"ok": False, "error": "User not found"}
        if (user.balance or 0) < amount:
            return {"ok": False, "error": "Insufficient balance"}
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
                })
        return {
            "ok": True,
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


if __name__ == "__main__":
    # Start ASGI server
    uvicorn.run(
        "bot.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=not settings.is_production
    )

