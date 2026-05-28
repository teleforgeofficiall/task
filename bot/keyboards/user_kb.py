"""
user_kb.py — All user-facing inline keyboards.
Professional casino-reward bot style.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💸 Tasks", callback_data="menu:tasks:0")],
        [
            InlineKeyboardButton("👛 Wallet", callback_data="menu:wallet"),
            InlineKeyboardButton("🤝 Refer", callback_data="menu:refer"),
        ],
        [
            InlineKeyboardButton("🎮 Games", callback_data="menu:snapgame"),
            InlineKeyboardButton("🎁 Daily Bonus", callback_data="menu:daily_bonus"),
        ],
        [
            InlineKeyboardButton("🔔 Alerts", callback_data="menu:alerts"),
        ],
        [
            InlineKeyboardButton("💰 Earn More", callback_data="menu:earn_more"),
            InlineKeyboardButton("💳 Withdraw", callback_data="menu:withdraw"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")],
    ])


def contact_keyboard() -> InlineKeyboardMarkup:
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Verify Phone Number", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


def fsub_keyboard(channels: List[dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for ch in channels:
        btn_text = f"📢 Join {ch.get('title', 'Channel')}"
        url = ch.get("invite_link") or ch.get("url", "")
        keyboard.append([InlineKeyboardButton(btn_text, url=url)])
    keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="fsub:verify")])
    return InlineKeyboardMarkup(keyboard)


def wallet_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📜 Transaction History", callback_data=f"wallet:transactions:0")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def tasks_list_keyboard(tasks: List[dict], page: int, total: int) -> InlineKeyboardMarkup:
    keyboard = []
    for t in tasks:
        desc = t["description"][:30] + ("..." if len(t["description"]) > 30 else "")
        keyboard.append([
            InlineKeyboardButton(f"{desc} — ₹{t['reward']:.2f}", callback_data=f"task:view:{t['id']}:{page}")
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"menu:tasks:{page-1}"))
    if page < total - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"menu:tasks:{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)


def task_detail_keyboard(task_id: int, task_type: str, url: str, page: int) -> InlineKeyboardMarkup:
    keyboard = []
    if task_type == "channel" and url:
        keyboard.append([InlineKeyboardButton("📢 Join Channel", url=url)])
        keyboard.append([InlineKeyboardButton("✅ Verify & Claim", callback_data=f"task:verify_channel:{task_id}:{page}")])
    elif task_type == "manual":
        keyboard.append([InlineKeyboardButton("📤 Submit Proof", callback_data=f"task:submit_proof:{task_id}:{page}")])
    keyboard.append([InlineKeyboardButton("🔙 Back to List", callback_data=f"menu:tasks:{page}")])
    return InlineKeyboardMarkup(keyboard)


def referral_keyboard(has_unclaimed: bool, ref_link: str = "") -> InlineKeyboardMarkup:
    keyboard = []
    if has_unclaimed:
        keyboard.append([InlineKeyboardButton("🎁 Claim Pending Rewards", callback_data="refer:claim")])
    if ref_link:
        keyboard.append([InlineKeyboardButton("📤 Share Referral Link", switch_inline_query=f"ref_{ref_link.split('ref_')[1].split(':')[0]}")])
    keyboard.append([
        InlineKeyboardButton("🏆 Top Referrers", callback_data="refer:top"),
        InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(keyboard)


def games_hub_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🎲 Dice", callback_data="game:play:dice"),
            InlineKeyboardButton("🎰 Slots", callback_data="game:play:slots"),
        ],
        [
            InlineKeyboardButton("💣 Mines", callback_data="game:play:mines"),
            InlineKeyboardButton("📈 Crash", callback_data="game:play:crash"),
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")],
    ]
    return InlineKeyboardMarkup(keyboard)


def game_bet_amount_keyboard(game: str) -> InlineKeyboardMarkup:
    amounts = [5, 10, 25, 50, 100]
    keyboard = []
    row = []
    for i, a in enumerate(amounts):
        row.append(InlineKeyboardButton(f"₹{a}", callback_data=f"game:bet:{game}:{a}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Games", callback_data="menu:snapgame")])
    return InlineKeyboardMarkup(keyboard)


def mines_grid_keyboard(revealed: List[str], game_over: bool) -> InlineKeyboardMarkup:
    grid_size = len(revealed)
    cols = 3
    keyboard = []
    for i in range(0, grid_size, cols):
        row = []
        for j in range(i, min(i + cols, grid_size)):
            cell = revealed[j]
            if cell == "gem":
                row.append(InlineKeyboardButton("💎", callback_data="mines:none"))
            elif cell == "mine":
                row.append(InlineKeyboardButton("💥", callback_data="mines:none"))
            else:
                row.append(InlineKeyboardButton("⬜", callback_data=f"mines:reveal:{j}"))
        keyboard.append(row)
    if not game_over:
        keyboard.append([InlineKeyboardButton("💰 Cash Out", callback_data="mines:cashout")])
    else:
        keyboard.append([InlineKeyboardButton("🔁 Play Again", callback_data="game:play:mines")])
        keyboard.append([InlineKeyboardButton("🔙 Games", callback_data="menu:snapgame")])
    return InlineKeyboardMarkup(keyboard)


def crash_game_keyboard(game_id: str, crashed: bool) -> InlineKeyboardMarkup:
    if crashed:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Play Again", callback_data="game:play:crash")],
            [InlineKeyboardButton("🔙 Games", callback_data="menu:snapgame")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Cash Out", callback_data=f"crash:cashout:{game_id}")],
    ])


def game_result_keyboard(game: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Play Again", callback_data=f"game:play:{game}")],
        [InlineKeyboardButton("🔙 Games", callback_data="menu:snapgame")],
    ])


def star_amount_keyboard() -> InlineKeyboardMarkup:
    star_vals = [1, 5, 10, 25, 50, 100]
    keyboard = []
    row = []
    for i, s in enumerate(star_vals):
        row.append(InlineKeyboardButton(f"{s}⭐ (₹{s*2})", callback_data=f"withdraw:stars_amount:{s}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="menu:withdraw")])
    return InlineKeyboardMarkup(keyboard)


def withdraw_amount_keyboard(method: str, extra: str = "") -> InlineKeyboardMarkup:
    amounts = [10, 25, 50, 100, 250, 500]
    keyboard = []
    row = []
    for i, a in enumerate(amounts):
        row.append(InlineKeyboardButton(f"₹{a}", callback_data=f"withdraw:amount_sel:{method}:{a}:{extra}"))
        if (i + 1) % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="menu:withdraw")])
    return InlineKeyboardMarkup(keyboard)


def daily_bonus_keyboard(can_claim: bool) -> InlineKeyboardMarkup:
    keyboard = []
    if can_claim:
        keyboard.append([InlineKeyboardButton("🎁 Claim Daily Bonus", callback_data="bonus:claim")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(keyboard)
