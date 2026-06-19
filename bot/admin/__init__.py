"""bot/admin package"""
from bot.admin import panel, dashboard, users, tasks, proofs, withdrawals, broadcast, settings, fsub, images, cmds, referral_cfg, security, earn_more_mgmt, alerts_mgmt, withdraw_config, game_config, export
from bot.admin import bonus_manage, redeem_code, extra_config
from bot.backup import register_handlers as register_backup_handlers

def register_admin_handlers(application) -> None:
    """Register all admin-facing command/callback/handler handlers."""
    panel.register_handlers(application)
    dashboard.register_handlers(application)
    users.register_handlers(application)
    tasks.register_handlers(application)
    proofs.register_handlers(application)
    withdrawals.register_handlers(application)
    broadcast.register_handlers(application)
    settings.register_handlers(application)
    fsub.register_handlers(application)
    images.register_handlers(application)
    earn_more_mgmt.register_handlers(application)
    alerts_mgmt.register_handlers(application)
    cmds.register_handlers(application)
    referral_cfg.register_handlers(application)
    security.register_handlers(application)
    withdraw_config.register_handlers(application)
    game_config.register_handlers(application)
    bonus_manage.register_handlers(application)
    redeem_code.register_handlers(application)
    extra_config.register_handlers(application)
    export.register_handlers(application)
    register_backup_handlers(application)
