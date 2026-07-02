"""Admin REST API layer for TASKHUB Mini App admin panel."""

import json
import logging
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from sqlalchemy import select, func, desc

from bot.database import get_session, Repository
from bot.database.models_sql import UserTable, TaskTable, ProofTable, WithdrawalTable
from bot.admin.panel import get_admin_ids, refresh_admin_ids

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")

UPLOAD_DIR = "/opt/taskhub/uploads"


@router.post("/upload-image")
async def admin_upload_image(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    image_data = data.get("image", "")
    prefix = data.get("prefix", "img")
    if not image_data:
        return {"ok": False, "error": "No image data"}
    import base64
    if "," in image_data:
        image_data = image_data.split(",")[1]
    try:
        img_bytes = base64.b64decode(image_data)
    except Exception:
        return {"ok": False, "error": "Invalid image data"}
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.jpg"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    return {"ok": True, "path": f"/api/app/uploads/{filename}"}


async def require_admin(request: Request) -> int:
    """Extract user_id from request and verify admin access. Never consumes request body."""
    try:
        user_id = request.query_params.get("user_id")
        if not user_id:
            if request.method == "GET":
                raise HTTPException(status_code=401, detail="Missing user_id")
            ct = request.headers.get("content-type", "")
            if "multipart/form-data" in ct or "application/x-www-form-urlencoded" in ct:
                raise HTTPException(status_code=401, detail="Missing user_id")
            else:
                body = await request.json()
                user_id = body.get("user_id")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing user_id")
    user_id = int(user_id)
    if user_id not in get_admin_ids():
        raise HTTPException(status_code=403, detail="Forbidden: Not an admin")
    return user_id


# Key mapping between canonical DB keys (used by Telegram admin) and
# frontend-facing keys (used by Mini App admin panel).
# Ensures both admin panels stay in sync.
CANONICAL_TO_FRONTEND: dict[str, str] = {
    "min_withdraw": "min_withdraw_upi",
    "max_withdraw": "max_withdraw_upi",
    "refer_paused": "referral_paused",
    "require_contact": "contact_mandatory",
    "fixed_referral_reward": "referral_fixed_reward",
    "random_reward_min": "referral_min_reward",
    "random_reward_max": "referral_max_reward",
}
FRONTEND_TO_CANONICAL: dict[str, str] = {v: k for k, v in CANONICAL_TO_FRONTEND.items()}


async def get_admin_repo():
    session = get_session()
    s = await session.__aenter__()
    return s, Repository(s)


# ─── Dashboard ─────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def admin_dashboard(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        total_users = await session.execute(select(func.count(UserTable.id)))
        total_users = total_users.scalar() or 0
        today_str = str(date.today())
        today_joins = await session.execute(
            select(func.count(UserTable.id)).where(UserTable.joined_at >= today_str)
        )
        today_joins = today_joins.scalar() or 0
        banned = await session.execute(
            select(func.count(UserTable.id)).where(UserTable.banned == True)
        )
        banned = banned.scalar() or 0
        flagged = await session.execute(
            select(func.count(UserTable.id)).where(UserTable.is_flagged == True)
        )
        flagged = flagged.scalar() or 0
        pending_proofs = await session.execute(
            select(func.count(ProofTable.id)).where(ProofTable.status == "pending")
        )
        pending_proofs = pending_proofs.scalar() or 0
        pending_withdrawals = await session.execute(
            select(func.count(WithdrawalTable.id)).where(WithdrawalTable.status == "pending")
        )
        pending_withdrawals = pending_withdrawals.scalar() or 0
        total_earnings = await session.execute(
            select(func.coalesce(func.sum(UserTable.lifetime_earnings), 0))
        )
        total_earnings = float(total_earnings.scalar() or 0)
        total_withdrawn = await session.execute(
            select(func.coalesce(func.sum(UserTable.total_withdrawals), 0))
        )
        total_withdrawn = float(total_withdrawn.scalar() or 0)
        active_users = await session.execute(
            select(func.count(UserTable.id))
            .where(UserTable.last_active_date >= (datetime.now() - timedelta(days=7)).isoformat())
        )
        active_users = active_users.scalar() or 0
        return {
            "ok": True,
            "total_users": total_users,
            "active_users_7d": active_users,
            "today_joins": today_joins,
            "banned": banned,
            "flagged": flagged,
            "pending_proofs": pending_proofs,
            "pending_withdrawals": pending_withdrawals,
            "total_earnings": total_earnings,
            "total_withdrawn": total_withdrawn,
        }


# ─── Users ─────────────────────────────────────────────────────────────────

@router.get("/users/search")
async def admin_users_search(request: Request, q: str = "", page: int = 0):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        query = select(UserTable).order_by(UserTable.id.desc())
        if q:
            q_clean = q.strip()
            if q_clean.isdigit():
                query = query.where(UserTable.user_id == int(q_clean))
            else:
                query = query.where(
                    UserTable.first_name.ilike(f"%{q_clean}%") |
                    UserTable.username.ilike(f"%{q_clean}%")
                )
        total = await session.execute(select(func.count()).select_from(query.subquery()))
        total = total.scalar() or 0
        rows = await session.execute(query.offset(page * 20).limit(20))
        users = []
        for r in rows.scalars().all():
            meta = r.user_meta or {}
            users.append({
                "id": r.user_id,
                "name": r.first_name,
                "username": r.username,
                "balance": float(r.balance or 0),
                "banned": r.banned,
                "is_flagged": r.is_flagged,
                "warnings": r.warnings,
                "withdraw_locked": r.withdraw_locked,
                "joined_at": r.joined_at,
                "last_active": r.last_active_date,
                "lifetime_earnings": float(r.lifetime_earnings or 0),
                "phone": r.phone_number or "",
                "upi": meta.get("upi", ""),
            })
        return {"ok": True, "users": users, "total": total, "page": page}


@router.get("/users/{target_id}")
async def admin_user_detail(request: Request, target_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        user = await repo.get_user(target_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        meta = dict(user.user_meta or {})
        proofs = await repo.get_user_pending_proofs(target_id)
        withdrawals = await repo.get_user_withdrawal_history(target_id, 10)
        transactions = await repo.get_user_transactions(target_id, 100)
        earnings_by_type = {}
        for tx in transactions:
            amt = tx.get("amount", 0)
            if amt > 0:
                ttype = tx.get("type", "other")
                earnings_by_type[ttype] = earnings_by_type.get(ttype, 0) + amt
        return {
            "ok": True,
            "user": {
                "id": user.user_id,
                "name": user.first_name,
                "username": user.username,
                "balance": float(user.balance or 0),
                "lifetime_earnings": float(user.lifetime_earnings or 0),
                "referral_earnings": float(user.referral_earnings or 0),
                "banned": user.banned,
                "ban_reason": user.ban_reason or "",
                "is_flagged": user.is_flagged,
                "warnings": user.warnings,
                "withdraw_locked": user.withdraw_locked,
                "joined_at": user.joined_at,
                "last_active": user.last_active_date,
                "completed_tasks": list(user.completed_tasks or []),
                "referrals": len(user.referrals or []),
                "phone": user.phone_number or "",
                "upi": meta.get("upi", ""),
                "device_verified": user.device_verified,
                "fraud_score": user.fraud_score,
            },
            "pending_proofs": len(proofs),
            "recent_withdrawals": withdrawals,
            "transactions": transactions,
            "earnings_by_type": earnings_by_type,
        }


@router.post("/users/{target_id}/ban")
async def admin_user_ban(request: Request, target_id: int):
    admin_id = await require_admin(request)
    data = await request.json()
    reason = data.get("reason", "")
    async with get_session() as session:
        repo = Repository(session)
        await repo.ban_user(target_id, admin_id, reason)
    return {"ok": True}


@router.post("/users/{target_id}/unban")
async def admin_user_unban(request: Request, target_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        await repo.unban_user(target_id, admin_id)
    return {"ok": True}


@router.post("/users/{target_id}/balance")
async def admin_user_balance(request: Request, target_id: int):
    admin_id = await require_admin(request)
    data = await request.json()
    amount = float(data.get("amount", 0))
    reason = data.get("reason", "")
    async with get_session() as session:
        repo = Repository(session)
        new_bal = await repo.admin_adjust_balance(admin_id, target_id, amount, reason)
    return {"ok": True, "new_balance": new_bal}


@router.post("/users/{target_id}/warn")
async def admin_user_warn(request: Request, target_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        warnings = await repo.add_warning(target_id, admin_id)
    return {"ok": True, "warnings": warnings}


@router.post("/users/{target_id}/unwarn")
async def admin_user_unwarn(request: Request, target_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        warnings = await repo.remove_warning(target_id, admin_id)
    return {"ok": True, "warnings": warnings}


@router.post("/users/{target_id}/lock")
async def admin_user_lock(request: Request, target_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        await repo.lock_withdrawal(target_id, admin_id)
    return {"ok": True}


@router.post("/users/{target_id}/unlock")
async def admin_user_unlock(request: Request, target_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        await repo.unlock_withdrawal(target_id, admin_id)
    return {"ok": True}


# ─── Tasks ─────────────────────────────────────────────────────────────────

@router.get("/tasks")
async def admin_tasks(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        tasks = await repo.get_all_tasks()
        result = []
        for t in tasks:
            result.append(t.to_dict())
        return {"ok": True, "tasks": result}


@router.post("/tasks")
async def admin_create_task(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        task_data = {
            "task_type": data.get("task_type", "manual"),
            "description": data.get("description", ""),
            "guide": data.get("guide", ""),
            "reward": float(data.get("reward", 0)),
            "image": data.get("image", ""),
            "task_image": data.get("task_image", ""),
            "media_type": data.get("media_type", "photo"),
            "video_url": data.get("video_url", ""),
            "steps": data.get("steps", []),
            "color": data.get("color", "#7b5ef8"),
            "color2": data.get("color2", "#5a3fd6"),
            "is_multi_reward": data.get("is_multi_reward", False),
            "offer_url": data.get("offer_url", ""),
            "channel_id": data.get("channel_id"),
            "channel_username": data.get("channel_username"),
            "channel_url": data.get("channel_url"),
            "channel_title": data.get("channel_title"),
        }
        task = await repo.create_task(task_data)
    return {"ok": True, "task": task.to_dict()}


@router.put("/tasks/{task_id}")
async def admin_update_task(request: Request, task_id: int):
    admin_id = await require_admin(request)
    data = await request.json()
    allowed = [
        "task_type", "description", "guide", "reward", "image", "task_image", "media_type",
        "video_url", "steps", "color", "color2",
        "is_multi_reward", "offer_url", "channel_id", "channel_username",
        "channel_url", "channel_title", "is_active",
    ]
    kwargs = {k: v for k, v in data.items() if k in allowed and v is not None}
    async with get_session() as session:
        repo = Repository(session)
        await repo.update_task_fields(task_id, **kwargs)
        task = await repo.get_task(task_id)
    return {"ok": True, "task": task.to_dict() if task else None}


@router.delete("/tasks/{task_id}")
async def admin_delete_task(request: Request, task_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        await session.execute(TaskTable.__table__.delete().where(TaskTable.id == task_id))
        await session.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/toggle")
async def admin_toggle_task(request: Request, task_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        task = await repo.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        new_state = not task.is_active
        await repo.update_task_fields(task_id, is_active=new_state)
    return {"ok": True, "is_active": new_state}


# ─── Proofs ────────────────────────────────────────────────────────────────

@router.get("/proofs/pending")
async def admin_proofs_pending(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        proofs = await repo.get_pending_proofs()
        result = []
        for p in proofs:
            user = await repo.get_user(p.get("user_id", 0))
            result.append({
                "id": p.get("id"),
                "user_id": p.get("user_id"),
                "user_name": user.first_name if user else "Unknown",
                "task_id": p.get("task_id"),
                "proof_file_id": p.get("proof_file_id", ""),
                "file_type": p.get("file_type", "photo"),
                "date": p.get("date", ""),
            })
        return {"ok": True, "proofs": result}


@router.post("/proofs/{proof_id}/approve")
async def admin_approve_proof(request: Request, proof_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        proof = await repo.get_proof(proof_id)
        if not proof:
            raise HTTPException(status_code=404, detail="Proof not found")
        await repo.update_proof_status(proof_id, "approved", admin_id=admin_id)
        task = await repo.get_task(proof["task_id"])
        if task:
            await repo.credit_balance(
                proof["user_id"], task.reward, "task_reward",
                f"Task #{proof['task_id']} completed"
            )
            completed = list(task.completed_tasks or [])
            if proof["task_id"] not in completed:
                completed.append(proof["task_id"])
                await repo.update_task_fields(proof["task_id"], completion_count=task.completion_count + 1)
            await repo.update_user_fields(proof["user_id"], completed_tasks=completed)
    return {"ok": True}


@router.post("/proofs/{proof_id}/reject")
async def admin_reject_proof(request: Request, proof_id: int):
    admin_id = await require_admin(request)
    data = await request.json()
    reason = data.get("reason", "Incorrect proof")
    async with get_session() as session:
        repo = Repository(session)
        await repo.update_proof_status(proof_id, "rejected", admin_id=admin_id, reason=reason)
    return {"ok": True}


# ─── Withdrawals ───────────────────────────────────────────────────────────

@router.get("/withdrawals/pending")
async def admin_withdrawals_pending(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        withdrawals = await repo.get_pending_withdrawals()
        result = []
        for w in withdrawals:
            user = await repo.get_user(w.get("user_id", 0))
            result.append({
                "id": w.get("id"),
                "user_id": w.get("user_id"),
                "user_name": user.first_name if user else "Unknown",
                "amount": float(w.get("amount", 0)),
                "method": w.get("method", "upi"),
                "upi_id": w.get("upi_id", ""),
                "date": w.get("date", ""),
                "channel_link": w.get("channel_link", ""),
                "stars": int(w.get("stars", 0)),
            })
        return {"ok": True, "withdrawals": result}


@router.post("/withdrawals/{wid}/approve")
async def admin_approve_withdrawal(request: Request, wid: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        await repo.update_withdrawal_status(wid, "paid", admin_id=admin_id)
    return {"ok": True}


@router.post("/withdrawals/{wid}/reject")
async def admin_reject_withdrawal(request: Request, wid: int):
    admin_id = await require_admin(request)
    data = await request.json()
    reason = data.get("reason", "Rejected by admin")
    async with get_session() as session:
        repo = Repository(session)
        w = await repo.get_withdrawal(wid)
        if w:
            await repo.credit_balance(w["user_id"], w["amount"], "withdrawal_refund", reason)
            await repo.update_withdrawal_status(wid, "rejected", admin_id=admin_id, reason=reason)
    return {"ok": True}


# ─── Settings ──────────────────────────────────────────────────────────────

@router.get("/settings")
async def admin_settings(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        all_settings = await repo.get_all_settings()
    exposed = {}
    for k, v in all_settings.items():
        exposed_key = CANONICAL_TO_FRONTEND.get(k, k)
        exposed[exposed_key] = v
    return {"ok": True, "settings": exposed}


@router.put("/settings")
async def admin_update_settings(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        for key, value in data.items():
            canonical = FRONTEND_TO_CANONICAL.get(key, key)
            if canonical in ("admin_ids",) and isinstance(value, list):
                from bot.admin.panel import PERMANENT_ADMIN_IDS
                merged = list(set(value) | PERMANENT_ADMIN_IDS)
                await repo.update_setting(canonical, merged)
                await refresh_admin_ids()
            elif canonical in ("ad_campaigns", "promoted_items", "fsub_channels",
                              "earn_more_items", "custom_commands"):
                await repo.update_setting(canonical, value)
            elif canonical in ("maintenance_mode", "refer_paused", "require_contact",
                               "device_verification_enabled", "redeem_stock_enabled"):
                await repo.update_setting(canonical, bool(value))
            elif canonical in ("welcome_bonus_amount", "min_withdraw", "max_withdraw",
                               "daily_withdraw_limit",
                               "fixed_referral_reward", "random_reward_min", "random_reward_max",
                               "promo_price"):
                await repo.update_setting(canonical, float(value))
            else:
                await repo.update_setting(canonical, value)
    return {"ok": True}


# ─── Promoted Items ────────────────────────────────────────────────────────

@router.get("/promoted")
async def admin_promoted(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        items = await repo.get_setting("promoted_items", [])
    return {"ok": True, "items": items if isinstance(items, list) else []}


@router.post("/promoted")
async def admin_add_promoted(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        items = await repo.get_setting("promoted_items", [])
        if not isinstance(items, list):
            items = []
        new_id = max([i.get("id", 0) for i in items], default=0) + 1
        item = {
            "id": new_id,
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "image": data.get("image", ""),
            "url": data.get("url", ""),
            "badge": data.get("badge", ""),
            "color": data.get("color", "#7b5ef8"),
            "active": data.get("active", True),
        }
        items.append(item)
        await repo.update_setting("promoted_items", items)
    return {"ok": True, "item": item}


@router.put("/promoted/{item_id}")
async def admin_update_promoted(request: Request, item_id: int):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        items = await repo.get_setting("promoted_items", [])
        for item in items:
            if item.get("id") == item_id:
                item.update({k: v for k, v in data.items() if v is not None})
                await repo.update_setting("promoted_items", items)
                return {"ok": True, "item": item}
    raise HTTPException(status_code=404, detail="Item not found")


@router.delete("/promoted/{item_id}")
async def admin_delete_promoted(request: Request, item_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        items = await repo.get_setting("promoted_items", [])
        items = [i for i in items if i.get("id") != item_id]
        await repo.update_setting("promoted_items", items)
    return {"ok": True}


# ─── Ad Campaigns ──────────────────────────────────────────────────────────

@router.get("/ads")
async def admin_ads(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        campaigns = await repo.get_setting("ad_campaigns", [])
    return {"ok": True, "ads": campaigns if isinstance(campaigns, list) else []}


@router.post("/ads")
async def admin_add_ad(request: Request):
    try:
        admin_id = await require_admin(request)
        data = await request.json()
        title = (data.get("title") or "").strip()
        if not title:
            return {"ok": False, "error": "Title is required"}
        try:
            reward = float(data.get("reward", 0))
        except (ValueError, TypeError):
            reward = 0.0
        async with get_session() as session:
            repo = Repository(session)
            campaigns = await repo.get_setting("ad_campaigns", [])
            if not isinstance(campaigns, list):
                campaigns = []
            new_id = max([a.get("id", 0) for a in campaigns], default=0) + 1
            ad = {
                "id": new_id,
                "title": title,
                "description": (data.get("description") or "").strip(),
                "image": (data.get("image") or "").strip(),
                "video_url": (data.get("video_url") or "").strip(),
                "url": (data.get("url") or "").strip(),
                "reward": reward,
                "active": data.get("active", True),
            }
            campaigns.append(ad)
            await repo.update_setting("ad_campaigns", campaigns)
        return {"ok": True, "ad": ad}
    except Exception as e:
        logger.exception("admin_add_ad failed: %s", e)
        return {"ok": False, "error": "Server error"}


@router.put("/ads/{ad_id}")
async def admin_update_ad(request: Request, ad_id: int):
    try:
        admin_id = await require_admin(request)
        data = await request.json()
        async with get_session() as session:
            repo = Repository(session)
            campaigns = await repo.get_setting("ad_campaigns", [])
            if not isinstance(campaigns, list):
                campaigns = []
            for ad in campaigns:
                if ad.get("id") == ad_id:
                    if "title" in data: ad["title"] = data["title"]
                    if "description" in data: ad["description"] = data["description"]
                    if "image" in data: ad["image"] = data["image"]
                    if "video_url" in data: ad["video_url"] = data["video_url"]
                    if "url" in data: ad["url"] = data["url"]
                    if "reward" in data:
                        try: ad["reward"] = float(data["reward"])
                        except (ValueError, TypeError): pass
                    if "active" in data: ad["active"] = data["active"]
                    break
            await repo.update_setting("ad_campaigns", campaigns)
        return {"ok": True, "ad": next((a for a in campaigns if a.get("id") == ad_id), None)}
    except Exception as e:
        logger.exception("admin_update_ad failed: %s", e)
        return {"ok": False, "error": "Server error"}


@router.delete("/ads/{ad_id}")
async def admin_delete_ad(request: Request, ad_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        campaigns = await repo.get_setting("ad_campaigns", [])
        campaigns = [a for a in campaigns if a.get("id") != ad_id]
        await repo.update_setting("ad_campaigns", campaigns)
    return {"ok": True}


# ─── User Submissions (ads, tasks, channels from users) ───────────────────

@router.get("/user-submissions")
async def admin_user_submissions(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        submissions = await repo.get_setting("pending_user_submissions", [])
    return {"ok": True, "submissions": submissions if isinstance(submissions, list) else []}


@router.post("/user-submissions/{sub_id}/approve")
async def admin_approve_submission(request: Request, sub_id: int):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        submissions = await repo.get_setting("pending_user_submissions", [])
        if not isinstance(submissions, list):
            submissions = []
        approved = []
        remaining = []
        for s in submissions:
            if s.get("id") == sub_id:
                s["status"] = "approved"
                s["reviewed_by"] = admin_id
                approved.append(s)
            else:
                remaining.append(s)
        await repo.update_setting("pending_user_submissions", remaining)
        # Create task/ad if needed
        for s in approved:
            if s.get("type") == "task":
                task_data = {
                    "task_type": "manual",
                    "description": s.get("description", ""),
                    "guide": s.get("details", ""),
                    "reward": float(s.get("reward", 0)),
                    "image": s.get("image", ""),
                    "is_active": True,
                }
                await repo.create_task(task_data)
            elif s.get("type") == "promoted":
                items = await repo.get_setting("promoted_items", [])
                if not isinstance(items, list):
                    items = []
                new_id = max([i.get("id", 0) for i in items], default=0) + 1
                _c = s.get("color", "#7b5ef8")
                items.append({
                    "id": new_id,
                    "title": s.get("title", ""),
                    "description": s.get("description", ""),
                    "image": s.get("image", ""),
                    "url": s.get("url", ""),
                    "color": _c,
                    "color1": _c,
                    "color2": _c,
                    "badge": "User Submission",
                    "active": True,
                })
                await repo.update_setting("promoted_items", items)
            elif s.get("type") == "ad":
                campaigns = await repo.get_setting("ad_campaigns", [])
                if not isinstance(campaigns, list):
                    campaigns = []
                new_id = max([a.get("id", 0) for a in campaigns], default=0) + 1
                campaigns.append({
                    "id": new_id,
                    "title": s.get("title", ""),
                    "description": s.get("description", ""),
                    "image": s.get("image", ""),
                    "url": s.get("url", ""),
                    "reward": float(s.get("reward", 0.05)),
                    "active": True,
                })
                await repo.update_setting("ad_campaigns", campaigns)
    return {"ok": True, "approved": approved}


@router.post("/user-submissions/{sub_id}/reject")
async def admin_reject_submission(request: Request, sub_id: int):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        submissions = await repo.get_setting("pending_user_submissions", [])
        if not isinstance(submissions, list):
            submissions = []
        for s in submissions:
            if s.get("id") == sub_id:
                s["status"] = "rejected"
                s["reviewed_by"] = admin_id
                s["reject_reason"] = data.get("reason", "")
        await repo.update_setting("pending_user_submissions", submissions)
    return {"ok": True}


# ─── Redeem Code Management ────────────────────────────────────────────────

@router.get("/redeem-codes")
async def admin_redeem_codes_list(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        codes = await repo.get_all_redeem_codes()
    return {"ok": True, "codes": codes}


@router.post("/redeem-codes")
async def admin_redeem_codes_add(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    codes_str = data.get("codes", "")
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return {"ok": False, "error": "Invalid amount"}
    code_list = [c.strip() for c in codes_str.replace(",", "\n").split("\n") if c.strip()]
    if not code_list:
        return {"ok": False, "error": "No codes provided"}
    async with get_session() as session:
        repo = Repository(session)
        count = await repo.add_redeem_codes(code_list, amount)
    return {"ok": True, "added": count, "message": f"{count} redeem codes added for ₹{amount:.0f}"}


@router.get("/redeem-settings")
async def admin_redeem_settings(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        threshold = int(await repo.get_setting("redeem_low_stock_threshold", 5))
        enabled = bool(await repo.get_setting("redeem_stock_enabled", True))
    return {"ok": True, "threshold": threshold, "enabled": enabled}


@router.put("/redeem-settings")
async def admin_update_redeem_settings(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        if "threshold" in data:
            await repo.update_setting("redeem_low_stock_threshold", int(data["threshold"]))
        if "enabled" in data:
            await repo.update_setting("redeem_stock_enabled", bool(data["enabled"]))
    return {"ok": True}


# ─── Promo Config (price + QR) ────────────────────────────────────────────

@router.get("/promo-config")
async def admin_promo_config(request: Request):
    admin_id = await require_admin(request)
    async with get_session() as session:
        repo = Repository(session)
        price = await repo.get_setting("promo_price", 50)
        qr = await repo.get_setting("promo_qr_image", "")
        desc = await repo.get_setting("promo_description", "One-time payment for featured promotion")
    proxy_url = ""
    if qr:
        proxy_url = "https://taskhub-app-ten.vercel.app/api/app/image/promo_qr_image"
    return {"ok": True, "promo_price": float(price), "promo_qr_image": qr, "promo_qr_proxy_url": proxy_url, "promo_description": desc}


@router.put("/promo-config")
async def admin_update_promo_config(request: Request):
    admin_id = await require_admin(request)
    data = await request.json()
    async with get_session() as session:
        repo = Repository(session)
        if "promo_price" in data:
            await repo.update_setting("promo_price", float(data["promo_price"]))
        if "promo_qr_image" in data:
            await repo.update_setting("promo_qr_image", data["promo_qr_image"])
        if "promo_description" in data:
            await repo.update_setting("promo_description", data["promo_description"])
    return {"ok": True}


