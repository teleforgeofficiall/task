from __future__ import annotations

import logging

from telegram import Update, BotCommand
from telegram.ext import ContextTypes, CommandHandler, filters
from telegram.constants import ParseMode

from bot.database import get_db, Repository
from bot.keyboards.user_kb import main_menu_keyboard
from bot.middlewares.auth import check_access
from bot.utils import edit_or_reply, escape_html

logger = logging.getLogger(__name__)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    repository = Repository(await get_db())

    passed = await check_access(update, context, repository)
    if not passed:
        return

    help_text = (
        "🆘 <b>Help & Support</b>\n\n"
        "Welcome to <b>TaskHub Rewards</b> — earn real money by completing simple tasks!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📌 <b>Available Commands</b>\n"
        "• <code>/start</code> — 🚀 Start your earning journey\n"
        "• <code>/help</code> — 🆘 Show this help message\n"
        "• <code>/promote</code> — 📢 Promote your own app/website/bot\n"
        "• <code>/admin</code> — 🛠️ Admin panel (admins only)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💸 <b>Sections Overview</b>\n\n"
        "• <b>Tasks</b> — Complete tasks like channel joins & manual tasks to earn rewards\n"
        "• <b>Wallet</b> — View your balance & transaction history\n"
        "• <b>Refer</b> — Invite friends & earn lifetime commission\n"
        "• <b>Games</b> — Play Dice, Slots, Mines & Crash to win rewards\n"
        "• <b>Daily Bonus</b> — Claim your free daily reward\n"
        "• <b>Alerts</b> — View important updates & announcements\n"
        "• <b>Earn More</b> — Browse additional earning opportunities\n"
        "• <b>Withdraw</b> — Withdraw your earnings directly to your wallet\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 <i>Need help? Contact the admin for support.</i>"
    )

    await update.message.reply_text(
        text=help_text,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


def register_handlers(application) -> None:
    application.add_handler(CommandHandler("help", help_command))
