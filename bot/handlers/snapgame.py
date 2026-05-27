from __future__ import annotations

import asyncio
import logging
import random
import time
from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

from bot.database import get_db, Repository
from bot.keyboards.user_kb import games_hub_keyboard, game_bet_amount_keyboard, mines_grid_keyboard, crash_game_keyboard
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
    banner_url = await repository.get_image("img_snap_pick")

    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎮 <b>TaskHub Games</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "> Pick a game and start playing.\n"
        "> All games use your wallet balance.\n\n"
        "🎲 <b>Dice</b> — Roll & win big\n"
        "🎰 <b>Slots</b> — Match symbols for rewards\n"
        "💣 <b>Mines</b> — Find gems, avoid bombs\n"
        "📈 <b>Crash</b> — Cash out before it crashes"
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
    game = query.data.split(":")[2]
    game_names = {"dice": "🎲 Dice", "slots": "🎰 Slots", "mines": "💣 Mines", "crash": "📈 Crash"}
    name = game_names.get(game, game.capitalize())

    text = f"{name}\n\nSelect your bet amount:"
    await edit_or_reply(update=update, context=context, text=text, reply_markup=game_bet_amount_keyboard(game))


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
    result_data = engine.roll_dice(cfg, gc, use_seeded=True)
    _increment_game_count(context)
    result = result_data["roll"]

    if result_data["win"]:
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

    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    await context.bot.send_message(
        chat_id=user_id,
        text="Select a game to play again 👇",
        reply_markup=games_hub_keyboard()
    )


# ─── Slots Game ──────────────────────────────────────────────────────────

async def game_slots_play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Place bet and spin 3 dice for slot machine."""
    query = update.callback_query
    if not query:
        return
    parts = query.data.split(":")
    amount = float(parts[3])
    user_id = query.from_user.id

    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    abuse = await engine.check_abuse(user_id, "slots", amount)
    if not abuse["allowed"]:
        await query.answer(f"❌ {abuse['reason']}", show_alert=True)
        return

    if not _check_cooldown(context, "slots"):
        await query.answer("⏳ Please wait before betting again.", show_alert=True)
        return

    user = await repository.get_user(user_id)
    if not user or user.balance < amount:
        await query.answer("❌ Insufficient balance!", show_alert=True)
        return

    await repository.record_game_bet_transaction(user_id, "slots", amount)
    await query.answer()

    await edit_or_reply(update=update, context=context, text="🎰 Spinning...")

    cfg = await engine.get_game_config("slots")
    gc = _get_game_count(context)
    spin = engine.spin_slots(cfg, gc)
    _increment_game_count(context)

    reels = spin["reels"]
    emoji_map = {"common": "🍒", "rare": "🔔", "epic": "⭐", "legendary": "👑"}
    display = " | ".join(emoji_map.get(s, "❓") for s in reels)

    if spin["win"]:
        mult = spin["multiplier"]
        payout = amount * mult
        await repository.record_game_win_transaction(user_id, "slots", payout, mult)
        await repository.record_game_round(user_id, "slots", amount, payout, mult, won=True, details={"reels": reels, "jackpot": spin.get("jackpot", False)})
        await engine.record_bet("slots", amount, payout)
        if spin.get("jackpot"):
            status = "JACKPOT! 🎉👑"
        elif len(set(reels)) == 1:
            status = "JACKPOT! 🎉"
        else:
            status = "Nice! ✅"
    else:
        mult = 0
        payout = 0
        await repository.record_game_round(user_id, "slots", amount, 0, 0, won=False, details={"reels": reels})
        await engine.record_bet("slots", amount, 0)
        status = "Lost ❌"

    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎰 <b>Slots</b> — Result\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<code>  {display}  </code>\n\n"
        f"<b>{status}</b>\n\n"
        f"Bet: <code>₹{amount:.2f}</code>\n"
        f"{f'Payout: <code>₹{payout:.2f} ({mult}x)</code>' if mult > 0 else ''}"
    )

    await context.bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
    await context.bot.send_message(
        chat_id=user_id,
        text="Select a game to play again 👇",
        reply_markup=games_hub_keyboard()
    )


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
    mine_data = engine.generate_mines(cfg, user_game_count=_get_game_count(context))

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
        engine = RiskEngine(repo)
        await repo.record_game_round(mines.get("_user_id") or query.from_user.id, "mines", mines["amount"], 0, mines["multiplier"], won=False)
        await engine.record_bet("mines", mines["amount"], 0)
        msg = "💥 Hit a mine!"
    else:
        mines["gems_found"] += 1
        engine = RiskEngine()
        cfg = await engine.get_game_config("mines")
        mines["multiplier"] = engine.get_mines_multiplier(mines["gems_found"], mines.get("mine_count", 3), mines.get("grid_size", 9))
        msg = "💎 Found a gem!"

    await query.answer(msg, show_alert=(cell == "mine"))
    context.user_data["mines"] = mines

    if mines["game_over"]:
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
    profit = payout - mines["amount"]
    sign = "+" if profit >= 0 else ""
    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    await repository.record_game_win_transaction(user_id, "mines", payout, mines["multiplier"])
    await repository.record_game_round(user_id, "mines", mines["amount"], payout, mines["multiplier"], won=True, details={"gems_found": mines.get("gems_found", 0)})
    await engine.record_bet("mines", mines["amount"], payout)
    _increment_game_count(context)
    await query.answer(f"💰 Cashed out {mines['multiplier']:.1f}x!", show_alert=True)

    mines["game_over"] = True
    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💣 <b>Mines</b> — Cashed Out!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> Cashed out at <b>{mines['multiplier']:.2f}x</b>\n\n"
        f"Bet: <code>₹{mines['amount']:.2f}</code>\n"
        f"Payout: <code>₹{payout:.2f}</code>\n"
        f"Profit: <code>{sign}₹{profit:.2f}</code>"
    )

    await edit_or_reply(update=update, context=context, text=text, reply_markup=mines_grid_keyboard(mines["revealed"], True))


# ─── Crash Game ──────────────────────────────────────────────────────────

async def game_crash_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a crash game round."""
    query = update.callback_query
    if not query:
        return
    parts = query.data.split(":")
    amount = float(parts[3])
    user_id = query.from_user.id

    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    abuse = await engine.check_abuse(user_id, "crash", amount)
    if not abuse["allowed"]:
        await query.answer(f"❌ {abuse['reason']}", show_alert=True)
        return

    user = await repository.get_user(user_id)
    if not user or user.balance < amount:
        await query.answer("❌ Insufficient balance!", show_alert=True)
        return

    await repository.record_game_bet_transaction(user_id, "crash", amount)
    await query.answer()

    cfg = await engine.get_game_config("crash")
    gc = _get_game_count(context)
    game_id = f"crash_{user_id}_{int(time.time())}"
    crash_point = engine.generate_crash_point(cfg, gc)
    start_time = time.time()

    try:
        chat_id = query.message.chat_id
        try:
            await query.delete_message()
        except Exception:
            pass
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"📈 <b>Crash</b>\n\nMultiplier: <code>1.00x</code>\n\n💰 Tap Cash Out before it crashes!",
            parse_mode="HTML",
            reply_markup=crash_game_keyboard(game_id, False)
        )
        chat_id = msg.chat_id
        msg_id = msg.message_id
    except Exception:
        chat_id = user_id
        msg_id = None

    context.user_data["crash"] = {
        "game_id": game_id,
        "amount": amount,
        "multiplier": 1.0,
        "crash_point": crash_point,
        "start_time": start_time,
        "cashed_out": False,
        "crashed": False,
        "chat_id": chat_id,
        "message_id": msg_id,
        "user_id": user_id,
    }

    asyncio.create_task(_crash_game_loop(context, game_id, amount, crash_point, start_time, chat_id, msg_id))


async def _crash_game_loop(context, game_id: str, amount: float, crash_point: float,
                           start_time: float, chat_id: int, msg_id: int) -> None:
    """Background game loop — runs concurrently with cashout handler."""
    user_data = context.user_data
    bot = context.bot
    try:
        for step in range(200):
            await asyncio.sleep(0.5)

            cd = user_data.get("crash")
            if not cd or cd.get("game_id") != game_id or cd["cashed_out"] or cd["crashed"]:
                return

            elapsed = time.time() - start_time
            new_mult = round(1.0 + (elapsed * 0.25), 2)

            # Re-read after potential yield during cashout processing
            cd = user_data.get("crash")
            if not cd or cd.get("game_id") != game_id or cd["cashed_out"] or cd["crashed"]:
                return

            cd["multiplier"] = new_mult
            user_data["crash"] = cd

            if new_mult >= crash_point:
                cd["crashed"] = True
                user_data["crash"] = cd
                try:
                    repo = Repository(await get_db())
                    uid = cd.get("user_id") or 0
                    await repo.record_game_round(uid, "crash", amount, 0, crash_point, won=False)
                    eng = RiskEngine(repo)
                    await eng.record_bet("crash", amount, 0)
                    _increment_game_count(context)
                except Exception:
                    pass
                if msg_id:
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id, message_id=msg_id,
                            text=f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📈 <b>Crash</b> — Crashed!\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"> 💥 Crashed at <b>{crash_point:.2f}x</b>\n\n"
                            f"Bet: <code>₹{amount:.2f}</code>\n"
                            f"Loss: <code>-₹{amount:.2f}</code>",
                            parse_mode="HTML",
                            reply_markup=crash_game_keyboard(game_id, True)
                        )
                    except Exception:
                        pass
                return

            if msg_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=msg_id,
                        text=f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📈 <b>Crash</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"Multiplier: <code>{new_mult:.2f}x</code>\n\n"
                        f"💰 Cash out before it crashes!",
                        parse_mode="HTML",
                        reply_markup=crash_game_keyboard(game_id, False)
                    )
                except Exception:
                    return
    except Exception as exc:
        logger.error("Crash game loop error: %s", exc)


async def game_crash_cashout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cash out from crash game."""
    query = update.callback_query
    if not query:
        return

    user_id = query.from_user.id
    crash_data = context.user_data.get("crash")

    if not crash_data:
        await query.answer("No active game found. Start a new one!", show_alert=True)
        return

    if crash_data["crashed"]:
        await show_crash_result(query, context, crash_data, user_id)
        return

    if crash_data["cashed_out"]:
        await query.answer("✅ Already cashed out!", show_alert=True)
        return

    crash_data["cashed_out"] = True
    context.user_data["crash"] = crash_data

    mult = crash_data["multiplier"]
    amount = crash_data["amount"]
    payout = amount * mult
    profit = payout - amount

    await query.answer()

    repository = Repository(await get_db())
    engine = RiskEngine(repository)
    await repository.record_game_win_transaction(user_id, "crash", payout, mult)
    await repository.record_game_round(user_id, "crash", amount, payout, mult, won=True)
    await engine.record_bet("crash", amount, payout)
    _increment_game_count(context)

    sign = "+" if profit >= 0 else ""
    result_text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 <b>Crash</b> — Cashed Out!\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"> Cashed out at <b>{mult:.2f}x</b>\n\n"
        f"Bet: <code>₹{amount:.2f}</code>\n"
        f"Payout: <code>₹{payout:.2f}</code>\n"
        f"Profit: <code>{sign}₹{profit:.2f}</code>"
    )
    result_kb = crash_game_keyboard(crash_data["game_id"], True)

    chat_id = crash_data.get("chat_id") or user_id
    msg_id = crash_data.get("message_id")
    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=result_text, parse_mode="HTML", reply_markup=result_kb
            )
            return
        except Exception as exc:
            logger.warning("Crash cashout edit failed: %s", exc)

    await context.bot.send_message(
        chat_id=user_id, text=result_text, parse_mode="HTML", reply_markup=result_kb
    )


async def show_crash_result(
    query, context, crash_data, user_id, fallback_msg: str = ""
) -> None:
    """Show crash result instead of 'already cashed out' error."""
    if crash_data and crash_data.get("crashed"):
        amount = crash_data.get("amount", 0)
        crash_point = crash_data.get("crash_point", 1.0)
        lost = amount
        result_text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Crash</b> — Crashed!\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"> 💥 Crashed at <b>{crash_point:.2f}x</b>\n\n"
            f"Bet: <code>₹{amount:.2f}</code>\n"
            f"Loss: <code>-₹{lost:.2f}</code>"
        )
        result_kb = crash_game_keyboard(crash_data.get("game_id", ""), True)
        await query.answer("Game crashed!", show_alert=True)
        msg_id = crash_data.get("message_id")
        chat_id = crash_data.get("chat_id") or user_id
        if msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=result_text, parse_mode="HTML", reply_markup=result_kb
                )
            except Exception:
                pass
        return

    await query.answer(
        fallback_msg or "Game already ended. Start a new one!",
        show_alert=True
    )


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
    application.add_handler(CallbackQueryHandler(game_bet_select_handler, pattern="^game:play:(dice|slots|mines|crash)$"))

    # Bet confirmations
    application.add_handler(CallbackQueryHandler(game_dice_play_handler, pattern=r"^game:bet:dice:\d+(\.\d+)?$"))
    application.add_handler(CallbackQueryHandler(game_slots_play_handler, pattern=r"^game:bet:slots:\d+(\.\d+)?$"))
    application.add_handler(CallbackQueryHandler(game_mines_start_handler, pattern=r"^game:bet:mines:\d+(\.\d+)?$"))
    application.add_handler(CallbackQueryHandler(game_crash_start_handler, pattern=r"^game:bet:crash:\d+(\.\d+)?$"))

    # Mines interactions
    application.add_handler(CallbackQueryHandler(game_mines_reveal_handler, pattern=r"^mines:reveal:\d$"))
    application.add_handler(CallbackQueryHandler(game_mines_cashout_handler, pattern="^mines:cashout$"))
    application.add_handler(CallbackQueryHandler(game_mines_none_handler, pattern="^mines:none$"))

    # Crash interactions
    application.add_handler(CallbackQueryHandler(game_crash_cashout_handler, pattern=r"^crash:cashout:crash_\d+_\d+$"))
