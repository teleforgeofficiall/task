"""
main.py — Application entry point.
Bootstraps python-telegram-bot and FastAPI into a unified event loop.
"""
from __future__ import annotations

import asyncio
import logging
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
            if settings.WEBHOOK_URL:
                webhook_uri = f"{settings.WEBHOOK_URL}/webhook"
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
                if not settings.WEBHOOK_URL:
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
