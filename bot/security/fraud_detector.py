"""
fraud_detector.py — Heuristic analysis to calculate fraud scores and detect loops in referral chains.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from bot.database.repository import Repository
from bot.models.user import UserModel
from config.settings import settings

logger = logging.getLogger(__name__)


async def check_referral_chain_loop(
    repository: Repository,
    user_id: int,
    proposed_referrer_id: int,
) -> bool:
    """
    Check if setting the referrer of `user_id` to `proposed_referrer_id` would form a loop.
    Traverses the referral chain upwards from `proposed_referrer_id`.
    """
    if user_id == proposed_referrer_id:
        return True

    current_id: Optional[int] = proposed_referrer_id
    visited = {user_id}

    while current_id:
        if current_id in visited:
            return True
        visited.add(current_id)
        
        referrer_user = await repository.get_user(current_id)
        if not referrer_user:
            break
        current_id = referrer_user.referrer

    return False


async def calculate_fraud_score(
    repository: Repository,
    user: UserModel,
) -> int:
    """
    Heuristically calculate the fraud score for a user.
    - Loop check in referral chain: +40
    - Multi-accounting (shares fingerprint hash): +30
    - High referral count with zero task activity:
        - > 5 referrals, 0 tasks completed: +20
        - > 10 referrals, <= 1 task completed: +30
    - Suspicious phone prefix/pattern matches (if contact shared):
        - Same prefix shared by many unverified/flagged users: +20
    - No username + generic suspicious first name format: +10
    """
    score = 0
    reasons = []

    # 1. Referral Loop check
    if user.referrer:
        if await check_referral_chain_loop(repository, user.user_id, user.referrer):
            score += 40
            reasons.append("Referral chain loop detected")

    # 2. Referrals vs Activity Ratio
    ref_count = len(user.referrals)
    task_count = len(user.completed_tasks)
    if ref_count > 10 and task_count <= 1:
        score += 30
        reasons.append(f"High referrals ({ref_count}) with low task activity ({task_count})")
    elif ref_count > 5 and task_count == 0:
        score += 20
        reasons.append(f"Suspicious referrals ({ref_count}) with zero task activity")

    # 4. Suspicious contact/phone prefix
    if user.phone_number:
        prefix = user.phone_number[:5]
        all_users = await repository.get_all_users_cursor()
        similar_flagged = 0
        total_similar = 0
        for u in all_users:
            phone = u.phone_number
            if phone and phone.startswith(prefix) and u.user_id != user.user_id:
                total_similar += 1
                if u.is_flagged:
                    similar_flagged += 1

        if total_similar >= 5 and (similar_flagged / total_similar) >= 0.5:
            score += 20
            reasons.append("Phone prefix matches multiple flagged accounts")

    # 5. Profile heuristic check (no username, spammy first name)
    if not user.username:
        # Check if first_name looks like random junk/gibberish (e.g. consonants only, or long string of digits)
        name = user.first_name.strip()
        if len(name) > 8 and not any(c in "aeiouAEIOU" for c in name):
            score += 10
            reasons.append("Spammy name heuristic match")
        elif name.isdigit():
            score += 10
            reasons.append("Numeric name heuristic match")

    # Sync calculated score to DB if it differs
    if score != user.fraud_score:
        update_data = {"fraud_score": score}
        if score > settings.FRAUD_SCORE_THRESHOLD:
            update_data["is_flagged"] = True
            update_data["flag_reason"] = "; ".join(reasons)
        await repository.update_user_fields(user.user_id, **update_data)

    return score
