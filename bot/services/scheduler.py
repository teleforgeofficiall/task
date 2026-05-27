"""
scheduler.py — Async background task runner for scheduled game cycles.
Handles Indian Standard Time (IST) scheduling for Snap Pick betting closing, results, and re-opening.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from bot.database.repository import Repository
from bot.services.snap_game import process_snap_result
from config.settings import settings

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


async def game_scheduler(bot, repository: Repository) -> None:
    """
    Background scheduler task.
    Monitors current IST time and executes scheduled game actions:
    - 09:45 IST: Close game bets (status="closed")
    - 10:00 IST: declare result (process payouts)
    - 10:30 IST: open game bets (status="open", reset pool)
    """
    logger.info("Initializing scheduled game cycle checker (IST timezone)...")

    # Track last executed date for each event to prevent multiple runs in the same minute
    # format: event_name -> last_run_date_string (YYYY-MM-DD)
    last_run = {
        "close": "",
        "result": "",
        "open": ""
    }

    # Ensure defaults in database are seeded first
    await repository.ensure_defaults()

    while True:
        try:
            # 1. Get current time in IST
            now = datetime.now(IST)
            today_str = now.strftime("%Y-%m-%d")
            hour = now.hour
            minute = now.minute

            # Load active schedule from settings
            close_h = settings.SNAP_CLOSE_HOUR
            close_m = settings.SNAP_CLOSE_MIN
            result_h = settings.SNAP_RESULT_HOUR
            result_m = settings.SNAP_RESULT_MIN
            open_h = settings.SNAP_OPEN_HOUR
            open_m = settings.SNAP_OPEN_MIN

            # 2. Check: CLOSE BETTING event
            if hour == close_h and minute >= close_m:
                if last_run["close"] != today_str:
                    gs = await repository.get_game_state()
                    if gs.get("auto_schedule", True):
                        await repository.update_game_state(status="closed")
                        logger.info("Scheduler: Closed Snap Pick betting for today.")
                        last_run["close"] = today_str

            # 3. Check: DECLARE RESULT event
            if hour == result_h and minute >= result_m:
                if last_run["result"] != today_str:
                    gs = await repository.get_game_state()
                    if gs.get("auto_schedule", True):
                        logger.info("Scheduler: Commencing result payout calculation.")
                        await process_snap_result(bot, repository)
                        last_run["result"] = today_str

            # 4. Check: RE-OPEN GAME event
            if hour == open_h and minute >= open_m:
                if last_run["open"] != today_str:
                    gs = await repository.get_game_state()
                    if gs.get("auto_schedule", True):
                        await repository.update_game_state(status="open")
                        await repository.clear_bets()
                        logger.info("Scheduler: Re-opened Snap Pick game for next round.")
                        last_run["open"] = today_str

            # Sleep 30 seconds before checking time again
            await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("Game scheduler task cancelled.")
            break
        except Exception as exc:
            logger.exception("Error in game scheduler loop: %s", exc)
            await asyncio.sleep(60) # Wait a bit on error to prevent CPU spin
