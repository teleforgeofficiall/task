"""
snap_game.py — Payout and declaration logic for the Snap Pick (Heads/Tails) game.
Weighted house edge logic: declares winner side with the smaller pool of bets.
"""
from __future__ import annotations

import logging
import random
from bot.database.repository import Repository
from bot.services.notifications import notify_user, notify_admins

logger = logging.getLogger(__name__)


async def process_snap_result(
    bot,
    repository: Repository,
) -> dict:
    """
    Process Snap Pick betting game results.
    - Sums bets on Heads vs Tails.
    - Declares the winner as the side with the smaller total bet value.
    - Credits 2.0x payouts to winners.
    - Sends individual win/lose messages.
    - Resets game state and logs to DB.
    """
    try:
        gs = await repository.get_game_state()
        if gs.get("status") != "open":
            logger.info("Snap game is not open. Result skip.")
            return {"status": "skipped", "reason": "game_not_open"}

        bets = gs.get("bets", {"heads": {}, "tails": {}})
        heads_bets = bets.get("heads", {})
        tails_bets = bets.get("tails", {})

        # Calculate pools
        heads_total = sum(float(amt) for amt in heads_bets.values())
        tails_total = sum(float(amt) for amt in tails_bets.values())

        if not heads_bets and not tails_bets:
            # No bets placed, close game silently and reopen
            await repository.update_game_state(
                status="closed",
                last_result="none",
                last_closed=repository._now_ist()
            )
            await repository.clear_bets()
            logger.info("Snap game closed with zero bets.")
            return {"status": "success", "winner": "none", "heads_pool": 0, "tails_pool": 0}

        # Weighted result logic: pick the side with the smaller total bet amount
        if heads_total < tails_total:
            winner = "heads"
            loser = "tails"
        elif tails_total < heads_total:
            winner = "tails"
            loser = "heads"
        else:
            # If pools are equal, pick randomly
            winner = random.choice(["heads", "tails"])
            loser = "tails" if winner == "heads" else "heads"

        winner_bets = bets.get(winner, {})
        loser_bets = bets.get(loser, {})

        # 1. Payout winners (2x return)
        winners_count = 0
        total_payout = 0.0
        for uid_str, amount in winner_bets.items():
            user_id = int(uid_str)
            bet_amt = float(amount)
            payout = bet_amt * 2.0
            
            # Credit balance & record transaction
            await repository.credit_balance(
                user_id=user_id,
                amount=payout,
                tx_type="game_win",
                description=f"Snap Pick win (Bet {winner.upper()} ₹{bet_amt})",
                ref_id=f"snap_win_{user_id}"
            )
            
            # Notify user
            win_text = (
                f"🎯 <b>Snap Pick Results Out!</b>\n\n"
                f"Result: 🪙 <b>{winner.upper()}</b>\n"
                f"Your Bet: ₹{bet_amt:.2f} on {winner.upper()}\n"
                f"Payout: 🎉 <b>₹{payout:.2f} (2x Win!)</b>\n\n"
                f"<i>Your balance has been credited. Use /start to view.</i>"
            )
            await notify_user(bot=bot, user_id=user_id, text=win_text)
            winners_count += 1
            total_payout += payout

        # 2. Notify losers
        losers_count = 0
        for uid_str, amount in loser_bets.items():
            user_id = int(uid_str)
            bet_amt = float(amount)
            
            lose_text = (
                f"🎯 <b>Snap Pick Results Out!</b>\n\n"
                f"Result: 🪙 <b>{winner.upper()}</b>\n"
                f"Your Bet: ₹{bet_amt:.2f} on {loser.upper()}\n"
                f"Outcome: 😭 <b>Lost (Better luck next time!)</b>\n\n"
                f"<i>Play again in the next round! Use /start to play.</i>"
            )
            await notify_user(bot=bot, user_id=user_id, text=lose_text)
            losers_count += 1

        # 3. Update DB states
        await repository.update_game_state(
            status="closed",
            last_result=winner,
            last_closed=repository._now_ist()
        )
        await repository.clear_bets()

        # 4. Log admin action
        await repository.log_admin_action(
            admin_id=0, # System event
            action="game_result_processed",
            target=winner,
            details={
                "heads_pool": heads_total,
                "tails_pool": tails_total,
                "winners": winners_count,
                "losers": losers_count,
                "total_payout": total_payout,
            }
        )

        # Notify admins
        await notify_admins(
            bot=bot,
            text=(
                f"🎯 <b>Snap Pick Round Processed</b>\n"
                f"Result: 🪙 <b>{winner.upper()}</b>\n"
                f"Heads Pool: ₹{heads_total:.2f} ({len(heads_bets)} bets)\n"
                f"Tails Pool: ₹{tails_total:.2f} ({len(tails_bets)} bets)\n"
                f"Payouts: ₹{total_payout:.2f} credited to {winners_count} users."
            )
        )

        return {
            "status": "success",
            "winner": winner,
            "heads_pool": heads_total,
            "tails_pool": tails_total,
            "winners": winners_count,
            "losers": losers_count,
        }
    except Exception as exc:
        logger.exception("Failed to declare Snap game result: %s", exc)
        return {"status": "error", "reason": str(exc)}
