"""
admin_kb.py — All admin-facing inline keyboards.
"""
from __future__ import annotations

import logging
from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


def admin_main_menu() -> InlineKeyboardMarkup:
    """Main Admin panel dashboard options."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Dashboard", callback_data="admin:dashboard"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="menu:leaderboard"),
        ],
        [
            InlineKeyboardButton("👥 Users", callback_data="admin:users_menu"),
        ],
        [
            InlineKeyboardButton("💸 Tasks", callback_data="admin:tasks_menu"),
            InlineKeyboardButton("📝 Proofs", callback_data="admin:proofs_menu"),
        ],
        [
            InlineKeyboardButton("💳 Withdrawals", callback_data="admin:withdraws_menu"),
            InlineKeyboardButton("🎫 Google Redeem", callback_data="admin:redeem_manager"),
        ],
        [
            InlineKeyboardButton("💰 Wd Config", callback_data="admin:withdraw_config"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast_menu"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="admin:settings_menu"),
            InlineKeyboardButton("🔒 Security", callback_data="admin:security_menu"),
        ],
        [
            InlineKeyboardButton("🚪 Close", callback_data="admin:close"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def back_to_admin() -> InlineKeyboardMarkup:
    """Returns to admin main menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:main")]
    ])


def users_menu() -> InlineKeyboardMarkup:
    """Users management menu."""
    keyboard = [
        [InlineKeyboardButton("🔍 Lookup User (ID/@Username)", callback_data="admin:user_lookup")],
        [InlineKeyboardButton("⚠️ Flagged/Suspicious Users", callback_data="admin:flagged_users:0")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def user_action_keyboard(user_id: int, is_banned: bool, is_flagged: bool, withdraw_locked: bool) -> InlineKeyboardMarkup:
    """Options for a specific user profile."""
    ban_label = "✅ Unban User" if is_banned else "🚫 Ban User"
    flag_label = "✅ Unflag User" if is_flagged else "🚩 Flag User"
    lock_label = "🔓 Unlock Withdraw" if withdraw_locked else "🔒 Lock Withdraw"

    keyboard = [
        [
            InlineKeyboardButton("💵 Edit Balance", callback_data=f"admin:usr_bal:{user_id}"),
            InlineKeyboardButton(lock_label, callback_data=f"admin:usr_lock:{user_id}"),
        ],
        [
            InlineKeyboardButton("⚠️ Add Warning", callback_data=f"admin:usr_warn_add:{user_id}"),
            InlineKeyboardButton("🩹 Rem Warning", callback_data=f"admin:usr_warn_rem:{user_id}"),
        ],
        [
            InlineKeyboardButton(ban_label, callback_data=f"admin:usr_ban:{user_id}"),
            InlineKeyboardButton(flag_label, callback_data=f"admin:usr_flag:{user_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="admin:users_menu"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def tasks_menu() -> InlineKeyboardMarkup:
    """Tasks management menu."""
    keyboard = [
        [InlineKeyboardButton("➕ Add New Task", callback_data="admin:task_add_type")],
        [InlineKeyboardButton("📋 List All Tasks", callback_data="admin:tasks_list:0")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def task_type_selection() -> InlineKeyboardMarkup:
    """Choose manual or channel task type."""
    keyboard = [
        [
            InlineKeyboardButton("✍️ Manual Verification Task", callback_data="admin:task_create:manual"),
            InlineKeyboardButton("📢 Telegram Channel Sub Task", callback_data="admin:task_create:channel"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin:tasks_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def task_action_keyboard(task_id: int, is_active: bool, page: int) -> InlineKeyboardMarkup:
    """Options for a specific task."""
    toggle_label = "⏸️ Pause Task" if is_active else "▶️ Resume Task"
    keyboard = [
        [
            InlineKeyboardButton(toggle_label, callback_data=f"admin:task_toggle:{task_id}:{page}"),
            InlineKeyboardButton("🗑️ Delete Task", callback_data=f"admin:task_del:{task_id}:{page}"),
        ],
        [
            InlineKeyboardButton("✏️ Edit Task", callback_data=f"admin:task_edit:{task_id}:{page}"),
            InlineKeyboardButton("🔙 Back to List", callback_data=f"admin:tasks_list:{page}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def proofs_menu() -> InlineKeyboardMarkup:
    """Proofs management menu."""
    keyboard = [
        [InlineKeyboardButton("⏳ Review Pending Proofs", callback_data="admin:proofs_queue:0")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def proof_review_keyboard(proof_id: int, page: int) -> InlineKeyboardMarkup:
    """Action buttons to approve or reject a task proof submission."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"admin:proof_decide:approve:{proof_id}:{page}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin:proof_decide:reject:{proof_id}:{page}"),
        ],
        [
            InlineKeyboardButton("❌ Reject with Reason", callback_data=f"admin:proof_reason:{proof_id}:{page}"),
            InlineKeyboardButton("🔙 Back to Queue", callback_data=f"admin:proofs_queue:{page}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def withdraws_menu(upi: int = 0, redeem: int = 0, stars: int = 0) -> InlineKeyboardMarkup:
    """Withdrawals management menu with live pending counts."""
    upi_label = f"⏳ UPI Pending ({upi})"
    stars_label = f"⭐ Stars Pending ({stars})"
    keyboard = [
        [InlineKeyboardButton(upi_label, callback_data="admin:withdraws_queue:0")],
        [InlineKeyboardButton(stars_label, callback_data="admin:stars_queue:0")],
        [InlineKeyboardButton("🎫 Google Redeem Manager", callback_data="admin:redeem_manager")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def redeem_code_manager_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ Add Code", callback_data="admin:rc_add_code")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin:rc_settings")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="admin:withdraws_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def redeem_code_settings_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🔽 Set Low Stock Threshold", callback_data="admin:rc_set_threshold")],
        [InlineKeyboardButton("🟢 Toggle Stock Enabled", callback_data="admin:rc_toggle")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin:redeem_manager")],
    ]
    return InlineKeyboardMarkup(keyboard)


def withdrawal_alert_keyboard(user_id: int, wid: int) -> InlineKeyboardMarkup:
    """Keyboard for withdrawal admin alert — view profile + go to queue."""
    keyboard = [
        [InlineKeyboardButton("👤 View User Profile", callback_data=f"admin:usr_profile_{user_id}")],
        [InlineKeyboardButton("💳 Go to Withdrawals", callback_data="admin:withdraws_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def withdraw_config_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("🔽 Set Min Amount", callback_data="admin:wc_set_min"),
            InlineKeyboardButton("🔼 Set Max Amount", callback_data="admin:wc_set_max"),
        ],
        [
            InlineKeyboardButton("📅 Set Daily Limit", callback_data="admin:wc_set_daily"),
            InlineKeyboardButton("⭐ Star Config", callback_data="admin:star_config"),
        ],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def star_config_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("⭐ Set Star Tiers", callback_data="admin:sc_set_tiers"),
            InlineKeyboardButton("🔽 Min Stars", callback_data="admin:sc_set_min_stars"),
        ],
        [
            InlineKeyboardButton("🔼 Max Stars", callback_data="admin:sc_set_max_stars"),
            InlineKeyboardButton("🟢 Toggle Enable", callback_data="admin:sc_toggle_enable"),
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="admin:withdraw_config")]
    ]
    return InlineKeyboardMarkup(keyboard)


def star_withdrawal_action_keyboard(wid: int, page: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve (Mark Paid)", callback_data=f"admin:star_decide:approve:{wid}:{page}"),
            InlineKeyboardButton("❌ Reject & Refund", callback_data=f"admin:star_decide:reject:{wid}:{page}"),
        ],
        [
            InlineKeyboardButton("❌ Reject with Reason", callback_data=f"admin:star_reason:{wid}:{page}"),
            InlineKeyboardButton("🔙 Back to Queue", callback_data=f"admin:stars_queue:{page}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def withdrawal_action_keyboard(wid: int, page: int) -> InlineKeyboardMarkup:
    """Approve/reject withdrawal requests."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve (Mark Paid)", callback_data=f"admin:wd_decide:approve:{wid}:{page}"),
            InlineKeyboardButton("❌ Reject & Refund", callback_data=f"admin:wd_decide:reject:{wid}:{page}"),
        ],
        [
            InlineKeyboardButton("❌ Reject with Reason", callback_data=f"admin:wd_reason:{wid}:{page}"),
            InlineKeyboardButton("🔙 Back to Queue", callback_data=f"admin:withdraws_queue:{page}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def broadcast_menu() -> InlineKeyboardMarkup:
    """Select target audience for broadcast."""
    keyboard = [
        [
            InlineKeyboardButton("👥 Broadcast to All Users", callback_data="admin:bc_start:all"),
            InlineKeyboardButton("🟢 Active Users (7 Days)", callback_data="admin:bc_start:active"),
        ],
        [
            InlineKeyboardButton("🔴 Inactive Users", callback_data="admin:bc_start:inactive"),
            InlineKeyboardButton("💰 Bonus Drop", callback_data="admin:bc_start:drop_rain"),
        ],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def broadcast_cancel_keyboard() -> InlineKeyboardMarkup:
    """Broadcast progress cancel handler."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Cancel Broadcast", callback_data="admin:bc_cancel")]
    ])


def settings_menu(require_contact: bool = True, refer_paused: bool = False, maintenance_on: bool = False) -> InlineKeyboardMarkup:
    """General settings dashboard."""
    referral_toggle = "🔴 Referrals Paused" if refer_paused else "🟢 Referrals Active"
    maintenance_toggle = "🔧 Maintenance ON" if maintenance_on else "🔧 Maintenance OFF"
    
    keyboard = [
        [
            InlineKeyboardButton(maintenance_toggle, callback_data="admin:set_toggle_maintenance"),
        ],
        [
            InlineKeyboardButton(referral_toggle, callback_data="admin:set_toggle_refer"),
            InlineKeyboardButton("👑 Admins", callback_data="admin:manage_admins"),
        ],
        [
            InlineKeyboardButton("📣 Force Subscribe", callback_data="admin:set_fsub"),
            InlineKeyboardButton("🔔 Alerts Set", callback_data="admin:alerts_mgmt"),
            InlineKeyboardButton("💰 Earn More Manage", callback_data="admin:earn_more_mgmt"),
        ],
        [
            InlineKeyboardButton("🤝 Referral Config", callback_data="admin:set_referral_config"),
            InlineKeyboardButton("🖼️ Replace Images", callback_data="admin:set_images"),
        ],
        [
            InlineKeyboardButton("✍️ Custom Messages", callback_data="admin:set_messages"),
            InlineKeyboardButton("📟 Custom Commands", callback_data="admin:set_custom_cmds"),
        ],
        [
            InlineKeyboardButton("🎁 Bonus Manage", callback_data="admin:bonus_menu"),
            InlineKeyboardButton("🎰 Game Config", callback_data="admin:game_cfg_menu"),
        ],
        [
            InlineKeyboardButton("💾 Backup & Restore", callback_data="admin:backup_menu"),
            InlineKeyboardButton("⚠️ Reset Data", callback_data="admin:reset_data_cli"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def fsub_channels_keyboard(channels: List[dict]) -> InlineKeyboardMarkup:
    """Fsub channels manager list."""
    keyboard = []
    for chan in channels:
        c_id = chan["id"]
        title = chan.get("title", f"Channel {c_id}")
        keyboard.append([InlineKeyboardButton(f"🗑️ Remove {title}", callback_data=f"admin:fsub_rem:{c_id}")])

    keyboard.append([InlineKeyboardButton("➕ Add Channel", callback_data="admin:fsub_add")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")])
    return InlineKeyboardMarkup(keyboard)


def referral_config_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Referral rewards selection mode."""
    keyboard = [
        [
            InlineKeyboardButton("Fixed (₹) Mode" + (" ✅" if mode == "fixed" else ""), callback_data="admin:ref_mode:fixed"),
            InlineKeyboardButton("Random Range Mode" + (" ✅" if mode == "random" else ""), callback_data="admin:ref_mode:random"),
            InlineKeyboardButton("Smart AI Mode" + (" ✅" if mode == "smart" else ""), callback_data="admin:ref_mode:smart"),
        ],
        [
            InlineKeyboardButton("🔧 Set Fixed Reward", callback_data="admin:ref_set_fixed"),
            InlineKeyboardButton("🔧 Set Random Range", callback_data="admin:ref_set_range"),
        ],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def images_manager_keyboard() -> InlineKeyboardMarkup:
    """List images that can be replaced."""
    keyboard = [
        [
            InlineKeyboardButton("📸 Welcome / Start Image", callback_data="admin:img_replace:img_welcome"),
            InlineKeyboardButton("📸 Promote Banner", callback_data="admin:img_replace:img_promote"),
        ],
        [
            InlineKeyboardButton("📸 Games Hub Banner", callback_data="admin:img_replace:img_game"),
            InlineKeyboardButton("📸 Dice Banner", callback_data="admin:img_replace:img_game_dice"),
        ],
        [
            InlineKeyboardButton("📸 Slots Banner", callback_data="admin:img_replace:img_game_slots"),
            InlineKeyboardButton("📸 Mines Banner", callback_data="admin:img_replace:img_game_mines"),
        ],
        [
            InlineKeyboardButton("📸 Crash Banner", callback_data="admin:img_replace:img_game_crash"),
            InlineKeyboardButton("📸 Referral Invite", callback_data="admin:img_replace:img_refer_new"),
        ],
        [
            InlineKeyboardButton("📸 Referral Paused", callback_data="admin:img_replace:img_refer_paused"),
            InlineKeyboardButton("📸 Daily Bonus", callback_data="admin:img_replace:img_bonus_drop"),
        ],
        [
            InlineKeyboardButton("📸 Force Subscribe", callback_data="admin:img_replace:img_channel_task"),
            InlineKeyboardButton("📸 Tasks List", callback_data="admin:img_replace:img_tasks_list"),
        ],
        [
            InlineKeyboardButton("📸 Leaderboard", callback_data="admin:img_replace:img_leaderboard"),
            InlineKeyboardButton("📸 Google Redeem", callback_data="admin:img_replace:img_redeem_success"),
        ],
        [
            InlineKeyboardButton("📸 Withdraw Redeem", callback_data="admin:img_replace:img_withdraw_redeem"),
            InlineKeyboardButton("📸 Withdraw Stars", callback_data="admin:img_replace:img_withdraw_stars"),
        ],
        [
            InlineKeyboardButton("📸 Withdraw UPI", callback_data="admin:img_replace:img_withdraw_upi"),
        ],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def messages_manager_keyboard() -> InlineKeyboardMarkup:
    """List template messages that can be customized."""
    keyboard = [
        [
            InlineKeyboardButton("📝 Edit Start/Welcome Text", callback_data="admin:msg_edit:start_message"),
            InlineKeyboardButton("📝 Edit Launch/Ad Text", callback_data="admin:msg_edit:launch_message"),
        ],
        [
            InlineKeyboardButton("📝 Edit Ban Notification", callback_data="admin:msg_edit:ban_message"),
        ],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def custom_cmds_keyboard(commands: dict) -> InlineKeyboardMarkup:
    """Custom command manager list."""
    keyboard = []
    for cmd in commands.keys():
        keyboard.append([InlineKeyboardButton(f"🗑️ Delete /{cmd}", callback_data=f"admin:cmd_del:{cmd}")])

    keyboard.append([InlineKeyboardButton("➕ Add Custom Command", callback_data="admin:cmd_add")])
    keyboard.append([InlineKeyboardButton("🔙 Back to Settings", callback_data="admin:settings_menu")])
    return InlineKeyboardMarkup(keyboard)


def security_menu(contact: bool = True, device: bool = False) -> InlineKeyboardMarkup:
    """Security dashboard with contact/device toggles and URL config."""
    contact_label = f"📞 Contact Mandatory: {'ON ✅' if contact else 'OFF ❌'}"
    device_label = f"🔐 Device Verification: {'ON ✅' if device else 'OFF ❌'}"
    keyboard = [
        [InlineKeyboardButton(contact_label, callback_data="admin:sec_toggle_contact")],
        [InlineKeyboardButton(device_label, callback_data="admin:sec_toggle_device")],
        [InlineKeyboardButton("🔧 Set Verification URL", callback_data="admin:sec_set_verif_url")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)


def export_menu() -> InlineKeyboardMarkup:
    """Select file to export from DB."""
    keyboard = [
        [
            InlineKeyboardButton("👥 Export Users (CSV)", callback_data="admin:exp:users:csv"),
            InlineKeyboardButton("👥 Export Users (JSON)", callback_data="admin:exp:users:json"),
        ],
        [
            InlineKeyboardButton("💳 Export Withdrawals (CSV)", callback_data="admin:exp:withdrawals:csv"),
            InlineKeyboardButton("💳 Export Withdrawals (JSON)", callback_data="admin:exp:withdrawals:json"),
        ],
        [
            InlineKeyboardButton("📝 Export Task Proofs (CSV)", callback_data="admin:exp:proofs:csv"),
            InlineKeyboardButton("📝 Export Task Proofs (JSON)", callback_data="admin:exp:proofs:json"),
        ],
        [
            InlineKeyboardButton("📜 Export Admin Logs (CSV)", callback_data="admin:exp:admin_logs:csv"),
            InlineKeyboardButton("📜 Export Admin Logs (JSON)", callback_data="admin:exp:admin_logs:json"),
        ],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin:main")]
    ]
    return InlineKeyboardMarkup(keyboard)
