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
from telegram import Update
from telegram.ext import ApplicationBuilder

from telegram.error import TelegramError

from bot.database import get_db, close_db, check_db_health, Repository, init_db
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles async startup and shutdown hooks cleanly."""
    try:
        _webhook_url = settings.WEBHOOK_URL
        if not _webhook_url:
            render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
            if render_url:
                _webhook_url = render_url
                logger.info("Auto-detected Render URL: %s", _webhook_url)

        # Initialize database tables and defaults
        await init_db()
        db = await get_db()
        repository = Repository(db)
        await repository.ensure_defaults()

        # Setup PTB Handlers and Middlewares
        setup_rate_limiter(ptb_app)
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

@app.get("/")
async def root():
    return Response(content="Bot is Running", media_type="text/plain")

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Render deployment."""
    db_healthy = await check_db_health()
    return {
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
    from bot.database import get_db, Repository
    db = await get_db()
    repo = Repository(db)
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
    from bot.database import get_db, Repository
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
    db = await get_db()
    repo = Repository(db)

    # Gate 1: User already verified?
    result = await db.execute(select(UserTable).where(UserTable.user_id == user_id))
    user = result.scalar_one_or_none()
    if user and user.device_verified:
        return {"ok": False, "error": "already_verified"}

    # Gate 2: Device hash already linked to a different user?
    existing_user = await repo.get_device_fingerprint_user(device_hash)
    if existing_user is not None:
        return {"ok": False, "error": "device_linked", "existing_user": existing_user}

    success = await repo.store_device_fingerprint(device_hash, user_id)
    if not success:
        return {"ok": False, "error": "storage_failed"}
    return {"ok": True, "message": "Device verified"}


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


if __name__ == "__main__":
    # Start ASGI server
    uvicorn.run(
        "bot.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=not settings.is_production
    )
