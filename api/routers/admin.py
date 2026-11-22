"""Admin panel API: overview, subscriptions, payments and manual plan grants."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from api.billing import PLANS, grant_plan, month_start
from api.db.models import ADMINS, Payment, Prediction, Role, Subscription, User, utcnow
from api.deps import DbSession, Offset, ResourceId, audit, require

router = APIRouter(prefix="/admin", tags=["admin"])
Admin = Annotated[User, Depends(require(*ADMINS))]


class GrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str = Field(pattern="^(free|pro|lab)$")
    days: int = Field(30, ge=1, le=366)


@router.get("/overview")
def overview(admin: Admin, db: DbSession):
    now = utcnow()
    roles = dict(db.execute(select(User.role, func.count()).group_by(User.role)).all())
    active = dict(db.execute(select(Subscription.plan, func.count())
                             .where(Subscription.current_period_end > now)
                             .group_by(Subscription.plan)).all())
    revenue = dict(db.execute(select(Payment.mode, func.coalesce(func.sum(Payment.amount_paise), 0))
                              .where(Payment.status == "paid").group_by(Payment.mode)).all())
    return {
        "users": {role.value: roles.get(role, 0) for role in Role},
        "active_subscriptions": {code: active.get(code, 0) for code in ("pro", "lab")},
        "revenue_paise": {"live": int(revenue.get("live", 0)), "test": int(revenue.get("test", 0))},
        "payments_paid": db.scalar(select(func.count()).where(Payment.status == "paid")) or 0,
        "results_this_month": db.scalar(select(func.count(Prediction.id))
                                        .where(Prediction.created_at >= month_start(now))) or 0,
    }


@router.get("/subscriptions")
def subscriptions(admin: Admin, db: DbSession,
                  limit: Annotated[int, Query(ge=1, le=200)] = 100, offset: Offset = 0):
    now = utcnow()
    rows = db.execute(select(Subscription, User.email, User.full_name)
                      .join(User, User.id == Subscription.user_id)
                      .order_by(Subscription.current_period_end.desc(), Subscription.id.desc())
                      .offset(offset).limit(limit)).all()
    return [{"user_id": s.user_id, "email": email, "full_name": name, "plan": s.plan,
             "current_period_end": s.current_period_end, "source": s.source,
             "active": s.current_period_end > now} for s, email, name in rows]


@router.get("/payments")
def payments(admin: Admin, db: DbSession,
             limit: Annotated[int, Query(ge=1, le=200)] = 100, offset: Offset = 0):
    rows = db.execute(select(Payment, User.email).join(User, User.id == Payment.user_id)
                      .order_by(Payment.created_at.desc(), Payment.id.desc())
                      .offset(offset).limit(limit)).all()
    return [{"id": p.id, "email": email, "plan": p.plan, "amount_paise": p.amount_paise,
             "currency": p.currency, "mode": p.mode, "status": p.status,
             "razorpay_order_id": p.razorpay_order_id,
             "razorpay_payment_id": p.razorpay_payment_id, "created_at": p.created_at,
             "paid_at": p.paid_at} for p, email in rows]


@router.post("/users/{user_id}/plan")
def set_plan(user_id: ResourceId, body: GrantIn, request: Request, admin: Admin, db: DbSession):
    """Grant a complimentary plan, or end the current one with plan 'free'."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    if body.plan == "free":
        row = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
        if row is not None:
            row.current_period_end = utcnow()
            row.source = "admin"
            row.updated_at = utcnow()
    else:
        row = grant_plan(db, user_id, body.plan, body.days, "admin")
    audit(db, admin, "set_plan", "user", user_id, {"plan": body.plan, "days": body.days}, request)
    db.commit()
    return {"user_id": user_id, "plan": body.plan, "plan_name": PLANS[body.plan].name,
            "current_period_end": row.current_period_end if row else None}
