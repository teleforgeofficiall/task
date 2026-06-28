"""
referral.py — Logic to evaluate referral milestones and credit rewards directly.
Gated by task completion counts and device verification.
"""
from __future__ import annotations

import logging
from bot.database.repository import Repository
from bot.services.notifications import notify_user

logger = logging.getLogger(__name__)


async def check_referral_success(
    repository: Repository,
    user_id: int,
    bot,
) -> bool:
    """
    Check if user_id's inviter is eligible for a referral reward.
    Gates:
    1. User must have a referrer
    2. User must not have already triggered their referral reward
    3. Referrer must not be banned
    4. Global referral paused toggle
    5. User must have completed >= refer_min_tasks
    6. Device verification (only if device_verification_enabled is True)

    If all gates pass:
    - Credit referrer with global fixed_referral_reward
    - Mark referral_reward_claimed=True on invitee
    - Notify referrer of the reward
    """
    try:
        user = await repository.get_user(user_id)
        if not user or not user.referrer:
            return False

        if user.referral_reward_claimed:
            return False

        referrer_id = user.referrer
        referrer = await repository.get_user(referrer_id)
        if not referrer or referrer.banned:
            return False

        refer_paused = await repository.get_setting("refer_paused", False)
        if refer_paused:
            logger.info("Referral rewards paused. Skipping referral check for user %d", user_id)
            return False

        min_tasks = await repository.get_setting("refer_min_tasks", 1)
        tasks_completed = len(user.completed_tasks)
        if tasks_completed < min_tasks:
            logger.info("Invitee %d has only completed %d/%d tasks. Referral pending.", user_id, tasks_completed, min_tasks)
            return False

        dev_verif_enabled = await repository.get_setting("device_verification_enabled", False)
        if dev_verif_enabled and not user.device_verified:
            logger.info("Invitee %d has completed tasks but is not device verified. Referral pending.", user_id)
            await notify_user(
                bot=bot,
                user_id=user_id,
                text=(
                    "💡 <b>Unlock Referral Rewards!</b>\n\n"
                    "<blockquote>You have completed the required tasks, but your device is not verified yet.\n"
                    "Please go to <b>💼 Wallet</b> and click <b>🔍 Verify Device</b> to unlock rewards for your inviter!</blockquote>"
                )
            )
            await notify_user(
                bot=bot,
                user_id=referrer_id,
                text=(
                    f"🤝 <b>New Referral Pending!</b>\n\n"
                    f"<blockquote>Your invitee <b>{user.first_name}</b> has completed the required tasks, "
                    f"but needs to verify their device. Once they verify, you will get the reward!</blockquote>"
                )
            )
            return False

        ref_amount = float(await repository.get_setting("fixed_referral_reward", 0.5))
        if ref_amount <= 0:
            logger.info("Referral reward amount is 0. Skipping credit for user %d", user_id)
            return False

        await repository.credit_balance(
            user_id=referrer_id, amount=ref_amount,
            tx_type="referral_reward",
            description=f"Referral reward from User #{user_id}",
            ref_id=str(user_id)
        )
        await repository.update_user_fields(user_id, referral_reward_claimed=True)

        await notify_user(
            bot=bot,
            user_id=referrer_id,
            text=(
                f"🎉 <b>Referral Reward!</b>\n\n"
                f"User <b>{user.first_name}</b> (#{user_id}) completed their first task.\n"
                f"Credited: <b>₹{ref_amount:.2f}</b> to your wallet."
            )
        )

        logger.info("Referral reward ₹%.2f credited to user %d for refer %d", ref_amount, referrer_id, user_id)
        return True
    except Exception as exc:
        logger.exception("Error in check_referral_success for user %d: %s", user_id, exc)
        return False
