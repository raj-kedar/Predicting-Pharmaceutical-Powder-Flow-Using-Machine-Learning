"""Plans, usage and Razorpay checkout."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from api.billing import (CURRENCY, PERIOD_DAYS, PLANS, activate_payment, current_subscription,
                         effective_plan, is_staff, usage_this_month, webhook_signature_valid)
from api.db.models import Payment
from api.deps import AppSettings, CurrentUser, DbSession, audit

router = APIRouter(prefix="/billing", tags=["billing"])
log = logging.getLogger("powderflow.billing")
_ID = r"^[A-Za-z0-9_]{6,64}$"


class OrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: str = Field(pattern="^(pro|lab)$")


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    razorpay_order_id: str = Field(pattern=_ID)
    razorpay_payment_id: str = Field(pattern=_ID)
    razorpay_signature: str = Field(pattern=r"^[a-f0-9]{64}$")


def _client(request: Request):
    client = request.app.state.razorpay
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Online payments are not configured on this server.")
    return client


@router.get("/plans")
def plans(settings: AppSettings):
    return {
        "currency": CURRENCY, "period_days": PERIOD_DAYS, "mode": settings.billing_mode,
        "key_id": settings.razorpay_key_id or None,
        "plans": [{"code": p.code, "name": p.name, "price_paise": p.price_paise,
                   "monthly_limit": p.monthly_limit, "ml": p.ml, "features": list(p.features)}
                  for p in PLANS.values()],
    }


@router.get("/me")
def my_plan(user: CurrentUser, db: DbSession):
    plan = effective_plan(db, user)
    sub = current_subscription(db, user)
    return {"plan": plan.code, "plan_name": plan.name, "staff": is_staff(user),
            "monthly_limit": plan.monthly_limit, "used_this_month": usage_this_month(db, user),
            "ml": plan.ml, "current_period_end": sub.current_period_end if sub else None}


@router.post("/orders")
def create_order(body: OrderIn, request: Request, user: CurrentUser, db: DbSession,
                 settings: AppSettings):
    client = _client(request)
    plan = PLANS[body.plan]
    try:
        order = client.create_order(plan.price_paise, CURRENCY, f"pf-u{user.id}",
                                    {"user_id": str(user.id), "plan": plan.code})
    except Exception as exc:
        log.error("Razorpay order creation failed: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not start the payment. Please try again.") from exc
    payment = Payment(user_id=user.id, plan=plan.code, amount_paise=plan.price_paise,
                      currency=CURRENCY, period_days=PERIOD_DAYS, mode=settings.billing_mode,
                      razorpay_order_id=order["id"])
    db.add(payment)
    db.flush()
    audit(db, user, "order", "payment", payment.id, {"plan": plan.code}, request)
    db.commit()
    return {"order_id": order["id"], "amount": plan.price_paise, "currency": CURRENCY,
            "key_id": settings.razorpay_key_id, "plan": plan.code, "plan_name": plan.name,
            "name": user.full_name, "email": user.email}


@router.post("/verify")
def verify(body: VerifyIn, request: Request, user: CurrentUser, db: DbSession):
    client = _client(request)
    payment = db.query(Payment).filter(Payment.razorpay_order_id == body.razorpay_order_id).first()
    if payment is None or payment.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown order")
    if not client.signature_valid(body.razorpay_order_id, body.razorpay_payment_id,
                                  body.razorpay_signature):
        audit(db, user, "payment_rejected", "payment", payment.id, {"reason": "signature"},
              request)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Payment signature is invalid.")
    try:
        paid = activate_payment(db, client, body.razorpay_order_id, body.razorpay_payment_id,
                                user, request)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This payment was already used for another order.") from exc
    plan = PLANS[paid.plan]
    sub = current_subscription(db, user)
    return {"ok": True, "plan": plan.code, "plan_name": plan.name,
            "current_period_end": sub.current_period_end if sub else None}


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request):
    """Backup path if the browser closes before /verify. Configure it in the Razorpay dashboard."""
    settings = request.app.state.settings
    body = await request.body()
    if not webhook_signature_valid(settings.razorpay_webhook_secret, body,
                                   request.headers.get("X-Razorpay-Signature", "")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")
    try:
        event = json.loads(body)
        entity = event["payload"]["payment"]["entity"]
        order_id, payment_id = entity["order_id"], entity["id"]
    except (ValueError, KeyError, TypeError):
        return {"ok": True, "ignored": True}
    if event.get("event") not in ("payment.captured", "order.paid") or not order_id:
        return {"ok": True, "ignored": True}

    def process():
        db = request.app.state.session_factory()
        try:
            activate_payment(db, request.app.state.razorpay, order_id, payment_id, None, request)
        except HTTPException as exc:
            log.warning("Webhook for %s not applied: %s", order_id, exc.detail)
        except IntegrityError:
            db.rollback()
        finally:
            db.close()

    if request.app.state.razorpay is not None:
        await run_in_threadpool(process)
    return {"ok": True}
