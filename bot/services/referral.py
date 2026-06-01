"""
referral.py — Logic to evaluate referral milestones and trigger claimable rewards.
Gated by task completion counts and device verification.
"""
from __future__ import annotations

import logging
from bot.database.repository import Repository
from bot.services.notifications import notify_user
from bot.keyboards.user_kb import referral_keyboard

logger = logging.getLogger(__name__)


async def check_referral_success(
    repository: Repository,
    user_id: int,
    bot,
) -> bool:
    """
    Check if user_id's inviter is eligible for a referral reward.
    Gates:
    1. Global referral paused toggle
    2. User must have a referrer
    3. User must not have already triggered their referral reward (referral_reward_claimed == False)
    4. Referrer must not be banned
    5. User must have completed >= refer_min_tasks
    6. Device verification (only if device_verification_enabled is True)
    
    If all gates pass:
    - Add user_id to referrer's unclaimed_referrals list
    - Mark referral_reward_claimed=True on invitee
    - Notify referrer with a claim notification
    """
    try:
        user = await repository.get_user(user_id)
        if not user or not user.referrer:
            return False

        if user.referral_reward_claimed:
            # Reward already processed for this invitation
            return False

        referrer_id = user.referrer
        referrer = await repository.get_user(referrer_id)
        if not referrer or referrer.banned:
            return False

        # Gate 1: Check if referrals are paused
        refer_paused = await repository.get_setting("refer_paused", False)
        if refer_paused:
            logger.info("Referral rewards paused. Skipping referral check for user %d", user_id)
            return False

        # Gate 5: Min Tasks completed check
        min_tasks = await repository.get_setting("refer_min_tasks", 1)
        tasks_completed = len(user.completed_tasks)
        if tasks_completed < min_tasks:
            logger.info("Invitee %d has only completed %d/%d tasks. Referral pending.", user_id, tasks_completed, min_tasks)
            return False

        # Gate 6: Device Verification check (only if enabled)
        dev_verif_enabled = await repository.get_setting("device_verification_enabled", False)
        if dev_verif_enabled and not user.device_verified:
            # Notify invitee to verify to help their referrer
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
            # Notify inviter that their referral is pending verification
            await notify_user(
                bot=bot,
                user_id=referrer_id,
                text=(
                    f"🤝 <b>New Referral Pending!</b>\n\n"
                    f"<blockquote>Your invitee <b>{user.first_name}</b> has completed the required tasks, "
                    f"but needs to verify their device. Once they verify, you can claim your reward!</blockquote>"
                )
            )
            return False

        # All gates passed! Add to referrer's unclaimed list
        await repository.add_unclaimed_referral(referrer_id, user_id)
        
        # Mark invitee as claimed/completed
        await repository.update_user_fields(user_id, referral_reward_claimed=True)
        
        # Notify inviter
        claim_kb = referral_keyboard(has_unclaimed=True)
        await notify_user(
            bot=bot,
            user_id=referrer_id,
            text=(
                f"🎉 <b>Referral Verified!</b>\n\n"
                f"<blockquote>Your invitee <b>{user.first_name}</b> completed their tasks and verified their device!\n"
                f"You have an unclaimed reward waiting. Go to the Refer section to claim it!</blockquote>"
            ),
            reply_markup=claim_kb
        )
        
        logger.info("Referral reward unlocked for referrer %d from invitee %d", referrer_id, user_id)
        return True
    except Exception as exc:
        logger.exception("Error in check_referral_success for user %d: %s", user_id, exc)
        return False
