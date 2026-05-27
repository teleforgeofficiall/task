from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.database import get_db, Repository
from bot.admin.panel import is_admin
from bot.services.risk_engine import RiskEngine
from bot.keyboards.admin_kb import settings_menu, back_to_admin

logger = logging.getLogger(__name__)


async def admin_game_config_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    repo = Repository(await get_db())
    engine = RiskEngine(repo)
    cfg = await engine.load_config()
    stats = cfg.get("stats", {})
    gcfg = cfg.get("global", {})
    text = (
        "🎰 <b>Game Configuration</b>\n\n"
        f"<b>Global Stats</b>\n"
        f"Total Rounds: <code>{stats.get('total_bets', 0)}</code>\n"
        f"Total Payouts: <code>₹{stats.get('total_payouts', 0):.2f}</code>\n"
        f"Biggest Win: <code>₹{stats.get('biggest_win', 0):.2f}</code>\n\n"
        f"<b>Global Settings</b>\n"
        f"Exposure Cap: <code>₹{gcfg.get('exposure_cap', 50000):.2f}</code>\n"
        f"Max Payout: <code>₹{gcfg.get('max_payout', 10000):.2f}</code>\n"
        f"New User Luck Rounds: <code>{gcfg.get('new_user_luck_rounds', 3)}</code>\n\n"
        "Select a game to configure:"
    )
    kb = [
        [InlineKeyboardButton("🎲 Dice", callback_data="admin:game_cfg:dice"),
         InlineKeyboardButton("🎰 Slots", callback_data="admin:game_cfg:slots")],
        [InlineKeyboardButton("💣 Mines", callback_data="admin:game_cfg:mines"),
         InlineKeyboardButton("📈 Crash", callback_data="admin:game_cfg:crash")],
        [InlineKeyboardButton("📊 Analytics", callback_data="admin:game_cfg:analytics")],
        [InlineKeyboardButton("🔧 Global Config", callback_data="admin:game_cfg:global")],
        [InlineKeyboardButton("🎯 Retention Config", callback_data="admin:game_cfg:retention"),
         InlineKeyboardButton("🛡 Anti-Abuse", callback_data="admin:game_cfg:anti_abuse")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")],
    ]
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    await query.answer()


async def admin_game_config_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    game = query.data.split(":")[2]
    context.user_data["admin_state"] = f"game_cfg_{game}"
    repo = Repository(await get_db())
    engine = RiskEngine(repo)
    cfg = await engine.load_config()
    if game == "global":
        gcfg = cfg.get("global", {})
        text = (
            "🔧 <b>Global Game Config</b>\n\n"
            f"New User Luck Rounds: <code>{gcfg.get('new_user_luck_rounds', 3)}</code>\n"
            f"New User RTP Boost: <code>{gcfg.get('new_user_rtp_boost', 10)}%</code>\n"
            f"Exposure Cap: <code>₹{gcfg.get('exposure_cap', 50000):.2f}</code>\n"
            f"Max Payout: <code>₹{gcfg.get('max_payout', 10000):.2f}</code>\n"
            f"Volatility: <code>{gcfg.get('volatility', 'normal')}</code>\n\n"
            "Send the setting to change in format:\n"
            "<code>key = value</code>\n\n"
            "<i>Keys: new_user_luck_rounds, new_user_rtp_boost, exposure_cap, max_payout, volatility</i>"
        )
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=back_to_admin())
        await query.answer()
        return
    if game == "analytics":
        analytics = await repo.get_all_games_analytics()
        lines = ["📊 <b>Game Analytics</b>\n"]
        for a in analytics:
            gname = a["game"].capitalize()
            lines.append(
                f"<b>{gname}</b>\n"
                f"Rounds: {a['total_rounds']} | Wins: {a['total_wins']}\n"
                f"RTP: {a['rtp']}% | Edge: {a['house_edge']}%\n"
                f"Profit: ₹{a['house_profit']:.2f}\n"
            )
        await query.edit_message_text(
            text="\n".join(lines), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="admin:game_cfg_menu")]
            ])
        )
        await query.answer()
        return

    if game in ("retention", "anti_abuse"):
        section = cfg.get(game, {})
        text = f"<b>{game.replace('_',' ').title()} Configuration</b>\n\n"
        text += "\n".join(f"<code>{k}</code>: {v}" for k, v in section.items())
        text += "\n\nSend the setting to change:\n<code>key = value</code>"
        await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=back_to_admin())
        await query.answer()
        return
    gcfg = cfg.get(game, {})
    text = (
        f"<b>{game.capitalize()} Configuration</b>\n\n"
        + "\n".join(f"<code>{k}</code>: {v}" for k, v in gcfg.items() if k != "weights")
    )
    weight_str = ""
    if "weights" in gcfg:
        weight_str = "\n" + "\n".join(f"  <code>{k}</code>: {v}" for k, v in gcfg["weights"].items())
    text += "\n" + weight_str if weight_str else ""
    text += (
        "\n\nSend the setting to change in format:\n"
        "<code>key = value</code>\n\n"
        f"<i>Valid keys: {', '.join(k for k in gcfg.keys() if k != 'weights')}</i>"
    )
    await query.edit_message_text(text=text, parse_mode="HTML", reply_markup=back_to_admin())
    await query.answer()


async def admin_game_config_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    admin_state = context.user_data.get("admin_state", "")
    if not admin_state.startswith("game_cfg_"):
        return
    game = admin_state.replace("game_cfg_", "")
    text = msg.text.strip()
    if "=" not in text:
        await msg.reply_text("Invalid format. Use: <code>key = value</code>", parse_mode="HTML")
        return
    key, val_str = text.split("=", 1)
    key = key.strip().lower()
    val_str = val_str.strip()
    repo = Repository(await get_db())
    engine = RiskEngine(repo)
    cfg = await engine.load_config()
    if game == "global":
        target = cfg.setdefault("global", {})
    else:
        g = cfg.setdefault(game, {})
        if key == "weights" or key in g.get("weights", {}):
            weight_key = key if key != "weights" else None
            weights = g.setdefault("weights", {})
            if weight_key:
                try:
                    weights[weight_key] = int(val_str)
                except ValueError:
                    await msg.reply_text("Weight must be an integer.")
                    return
            else:
                await msg.reply_text("Use: common = 60")
                return
            await engine.save_config(cfg)
            await msg.reply_text(f"✅ Weight <code>{key}</code> updated to {val_str}", parse_mode="HTML")
            return
        target = g
    try:
        if "." in val_str or val_str.count("e") > 0:
            target[key] = float(val_str)
        elif val_str.isdigit():
            target[key] = int(val_str)
        elif val_str.lower() in ("true", "false"):
            target[key] = val_str.lower() == "true"
        else:
            target[key] = val_str
    except ValueError:
        target[key] = val_str
    await engine.save_config(cfg)
    await msg.reply_text(
        f"✅ <code>{key}</code> updated to {target[key]}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔙 Back to {game.capitalize()}", callback_data=f"admin:game_cfg:{game}")]
        ])
    )


async def admin_game_config_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not is_admin(query.from_user.id):
        return
    context.user_data.pop("admin_state", None)
    await admin_game_config_menu(update, context)


def register_handlers(application) -> None:
    application.add_handler(CallbackQueryHandler(admin_game_config_menu, pattern="^admin:game_cfg_menu$"))
    application.add_handler(CallbackQueryHandler(admin_game_config_detail, pattern=r"^admin:game_cfg:(dice|slots|mines|crash|global|analytics|retention|anti_abuse)$"))
    application.add_handler(CallbackQueryHandler(admin_game_config_back, pattern="^admin:game_cfg_back$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_game_config_input), group=12)
