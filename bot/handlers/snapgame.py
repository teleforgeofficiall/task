from __future__ import annotations

import asyncio
import logging
import random
import time
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import games_hub_keyboard, game_bet_amount_keyboard, mines_grid_keyboard, crash_game_keyboard, game_result_keyboard
from bot.services.risk_engine import RiskEngine
from bot.utils import edit_or_reply

logger = logging.getLogger(__name__)

_engine: RiskEngine = RiskEngine()


def _get_game_count(context) -> int:
    return context.user_data.get("game_count", 0)


def _increment_game_count(context) -> int:
    cnt = context.user_data.get("game_count", 0) + 1
    context.user_data["game_count"] = cnt
    return cnt


def _check_cooldown(context, game: str) -> bool:
    key = f"{game}_last_play"
    last = context.user_data.get(key, 0.0)
    if time.time() - last < 2.0:
        return False
    context.user_data[key] = time.time()
    return True

# ─── Games Hub ────────────────────────────────────────────────────────────

async def games_hub_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the games hub with all 4 games."""
    query = update.callback_query
    if not query:
        return

    repository = Repository(await get_db())
    banner_url = await repository.get_image("img_game")

    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 <b>TaskHub Games</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "> Pick a game and start playing.\n"
        "> All games use your wallet balance.\n\n"
        "🎲 <b>Dice</b> — Roll & win big\n"
        "💣 <b>Mines</b> — Find gems, avoid bombs"
    )

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        image_url=banner_url,
        reply_markup=games_hub_keyboard()
    )


# ─── Bet Amount Selection ────────────────────────────────────────────────

async def game_bet_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bet amount selection for a specific game."""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    game = query.data.split(":")[2]
    repository = Repository(await get_db())
    game_names = {"dice": "🎲 Dice", "mines": "💣 Mines"}
    name = game_names.get(game, game.capitalize())

    img_key = {"dice": "img_game_dice", "mines": "img_game_mines"}.get(game, "img_game")
    banner_url = await repository.get_image(img_key)
    descriptions = {
        "dice": (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{name}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🎯 How to Play</b>\n"
            "• Place your bet and roll the dice.\n"
            "• If you roll <b>4, 5, or 6</b> — <b>you win!</b>\n"
            "• Roll <b>1, 2, or 3</b> — you lose.\n"
            "• Higher rolls can trigger bigger multipliers.\n\n"
            "<b>💡 Tip:</b> Dice is fast-paced. Set a budget and play smart."
        ),
        "mines": (
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{name}\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>🎯 How to Play</b>\n"
            "• Place your bet to reveal a 3×3 grid.\n"
            "• Tap tiles to find 💎 gems — avoid 💣 bombs!\n"
            "• Each gem found increases your multiplier.\n"
            "• <b>Cash out</b> anytime to secure your winnings.\n"
            "• Hit a mine and you lose your bet.\n\n"
            "<b>💡 Tip:</b> Don't get greedy — cash out early for consistent wins."
        ),
    }
    text = descriptions.get(game, f"━━━━━━━━━━━━━━━━━━━━\n{name}\n━━━━━━━━━━━━━━━━━━━━\n\n<blockquote>Choose your bet amount and start playing.</blockquote>")
    await edit_or_reply(update=update, context=context, text=text, image_url=banner_url, reply_markup=game_bet_amount_keyboard(game))


# ─── Dice Game ────────────────────────────────────────────────────────────

async def game_dice_play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Place bet and roll the dice."""
    query = update.callback_query
    if not query:
        return
    parts = query.data.split(":")
    amount = float(parts[3])
    user_id = query.from_user.id

    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    abuse = await engine.check_abuse(user_id, "dice", amount)
    if not abuse["allowed"]:
        await query.answer(f"❌ {abuse['reason']}", show_alert=True)
        return

    if not _check_cooldown(context, "dice"):
        await query.answer("⏳ Please wait before betting again.", show_alert=True)
        return

    user = await repository.get_user(user_id)
    if not user or user.balance < amount:
        await query.answer("❌ Insufficient balance!", show_alert=True)
        return

    await repository.record_game_bet_transaction(user_id, "dice", amount)
    await query.answer()

    await edit_or_reply(update=update, context=context, text="🎲 Rolling...")
    cfg = await engine.get_game_config("dice")
    gc = _get_game_count(context)
    result_data = await engine.roll_dice(cfg, gc, use_seeded=True, user_id=user_id)
    _increment_game_count(context)
    result = result_data["roll"]
    won = result_data["win"]

    if won:
        mult = result_data["multiplier"]
        payout = amount * mult
        await repository.record_game_win_transaction(user_id, "dice", payout, mult)
        await repository.record_game_round(user_id, "dice", amount, payout, mult, won=True)
        await engine.record_bet("dice", amount, payout)
        text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎲 <b>Dice</b> — Result\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> You rolled <b>{result}</b>\n\n"
            f"<b>✅ You Win!</b>\n\n"
            f"Bet: <code>₹{amount:.2f}</code>\n"
            f"Payout: <code>₹{payout:.2f} ({mult}x)</code>"
        )
    else:
        await repository.record_game_round(user_id, "dice", amount, 0, 0, won=False)
        await engine.record_bet("dice", amount, 0)
        text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎲 <b>Dice</b> — Result\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> You rolled <b>{result}</b>\n\n"
            f"<b>❌ You Lost</b>\n\n"
            f"Bet: <code>₹{amount:.2f}</code>"
        )

    is_rage = await engine.is_rage_betting(user_id, amount)
    await engine.update_session(user_id, "dice", amount, won, is_rage)
    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML", reply_markup=game_result_keyboard("dice"))




# ─── Mines Game ──────────────────────────────────────────────────────────

async def game_mines_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a mines game."""
    query = update.callback_query
    if not query:
        return
    parts = query.data.split(":")
    amount = float(parts[3])
    user_id = query.from_user.id

    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    abuse = await engine.check_abuse(user_id, "mines", amount)
    if not abuse["allowed"]:
        await query.answer(f"❌ {abuse['reason']}", show_alert=True)
        return

    user = await repository.get_user(user_id)
    if not user or user.balance < amount:
        await query.answer("❌ Insufficient balance!", show_alert=True)
        return

    cfg = await engine.get_game_config("mines")
    user_prof = await engine.get_profile(user_id)
    profit_lvl = user_prof.get("meta", {}).get("net_profit", 0) if user_prof else 0
    mine_data = await engine.generate_mines(
        cfg, user_game_count=_get_game_count(context), user_id=user_id,
        profit_level=profit_lvl, loss_streak=user.consecutive_losses or 0
    )

    context.user_data["mines"] = {
        "board": mine_data["board"],
        "revealed": [""] * mine_data["grid_size"],
        "amount": amount,
        "multiplier": 1.0,
        "mine_count": mine_data["mines"],
        "grid_size": mine_data["grid_size"],
        "game_over": False,
        "gems_found": 0,
    }

    await repository.record_game_bet_transaction(user_id, "mines", amount)
    await query.answer()
    await show_mines_board(update, context)


async def show_mines_board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the current mines board."""
    query = update.callback_query
    mines = context.user_data.get("mines")
    if not mines:
        return

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💣 <b>Mines</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> Find gems, avoid bombs\n\n"
        f"Multiplier: <b>{mines['multiplier']:.2f}x</b>\n"
        f"Potential win: <code>₹{mines['amount'] * mines['multiplier']:.2f}</code>\n\n"
        f"Tap a tile to reveal:"
    )

    await edit_or_reply(
        update=update,
        context=context,
        text=text,
        reply_markup=mines_grid_keyboard(mines["revealed"], mines["game_over"])
    )


async def game_mines_reveal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reveal a mines tile."""
    query = update.callback_query
    if not query:
        return
    idx = int(query.data.split(":")[2])
    mines = context.user_data.get("mines")
    if not mines or mines["game_over"]:
        await query.answer("Game is over!", show_alert=False)
        return
    if mines["revealed"][idx]:
        await query.answer("Already revealed!", show_alert=False)
        return

    cell = mines["board"][idx]
    mines["revealed"][idx] = cell

    if cell == "mine":
        mines["game_over"] = True
        repo = Repository(await get_db())
        eng = RiskEngine(repo)
        await repo.record_game_round(mines.get("_user_id") or query.from_user.id, "mines", mines["amount"], 0, mines["multiplier"], won=False)
        await eng.record_bet("mines", mines["amount"], 0)
        msg = "💥 Hit a mine!"
    else:
        mines["gems_found"] += 1
        eng = RiskEngine(Repository(await get_db()))
        cfg = await eng.get_game_config("mines")
        mines["multiplier"] = eng.get_mines_multiplier(mines["gems_found"], mines.get("mine_count", 3), mines.get("grid_size", 9))
        msg = "💎 Found a gem!"

    await query.answer(msg, show_alert=(cell == "mine"))
    context.user_data["mines"] = mines

    if mines["game_over"]:
        user_id = query.from_user.id
        is_rage = await eng.is_rage_betting(user_id, mines["amount"])
        await eng.update_session(user_id, "mines", mines["amount"], False, is_rage)
        text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💣 <b>Mines</b> — Game Over\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> 💥 You hit a mine!\n\n"
            f"Loss: <code>-₹{mines['amount']:.2f}</code>"
        )
        await edit_or_reply(update=update, context=context, text=text, reply_markup=mines_grid_keyboard(mines["revealed"], True))
    else:
        await show_mines_board(update, context)


async def game_mines_cashout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cash out from mines game."""
    query = update.callback_query
    if not query:
        return
    mines = context.user_data.get("mines")
    if not mines or mines["game_over"]:
        return

    user_id = query.from_user.id
    payout = mines["amount"] * mines["multiplier"]
    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    await repository.record_game_win_transaction(user_id, "mines", payout, mines["multiplier"])
    await repository.record_game_round(user_id, "mines", mines["amount"], payout, mines["multiplier"], won=True, details={"gems_found": mines.get("gems_found", 0)})
    await engine.record_bet("mines", mines["amount"], payout)
    _increment_game_count(context)
    await query.answer(f"💰 Cashed out {mines['multiplier']:.1f}x!", show_alert=True)

    mines["game_over"] = True
    is_rage = await engine.is_rage_betting(user_id, mines["amount"])
    await engine.update_session(user_id, "mines", mines["amount"], True, is_rage)
    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💣 <b>Mines</b> — Cashed Out!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> Cashed out at <b>{mines['multiplier']:.2f}x</b>\n\n"
        f"Bet: <code>₹{mines['amount']:.2f}</code>\n"
        f"Payout: <code>₹{payout:.2f}</code>"
    )

    await edit_or_reply(update=update, context=context, text=text, reply_markup=mines_grid_keyboard(mines["revealed"], True))


async def game_mines_none_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle taps on already-revealed or game-over mines cells."""
    query = update.callback_query
    if not query:
        return
    await query.answer("Game is over — start a new one!", show_alert=False)


# ─── Handler Registration ────────────────────────────────────────────────

def register_handlers(application) -> None:
    """Register games handlers."""
    application.add_handler(CallbackQueryHandler(games_hub_handler, pattern="^menu:snapgame$"))

    # Game selection
    application.add_handler(CallbackQueryHandler(game_bet_select_handler, pattern="^game:play:(dice|mines)$"))

    # Bet confirmations
    application.add_handler(CallbackQueryHandler(game_dice_play_handler, pattern=r"^game:bet:dice:\d+(\.\d+)?$"))
    application.add_handler(CallbackQueryHandler(game_mines_start_handler, pattern=r"^game:bet:mines:\d+(\.\d+)?$"))

    # Mines interactions
    application.add_handler(CallbackQueryHandler(game_mines_reveal_handler, pattern=r"^mines:reveal:\d$"))
    application.add_handler(CallbackQueryHandler(game_mines_cashout_handler, pattern="^mines:cashout$"))
    application.add_handler(CallbackQueryHandler(game_mines_none_handler, pattern="^mines:none$"))
