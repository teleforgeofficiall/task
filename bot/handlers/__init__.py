"""bot/handlers package"""
from bot.handlers import start, wallet, tasks, referral, withdraw, snapgame, daily_bonus, leaderboard, contact, alerts, inline_share, earn_more, help_cmd

def register_user_handlers(application) -> None:
    """Register all user-facing command/callback/message handlers."""
    start.register_handlers(application)
    wallet.register_handlers(application)
    tasks.register_handlers(application)
    referral.register_handlers(application)
    withdraw.register_handlers(application)
    snapgame.register_handlers(application)
    earn_more.register_handlers(application)
    daily_bonus.register_handlers(application)
    leaderboard.register_handlers(application)
    contact.register_handlers(application)
    alerts.register_handlers(application)
    inline_share.register_handlers(application)
    help_cmd.register_handlers(application)
