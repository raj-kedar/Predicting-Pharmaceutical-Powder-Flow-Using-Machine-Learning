"""
Plans, usage limits and Razorpay payments.

Payments use Razorpay Orders for a 30-day pass per purchase. The amount always
comes from PLANS on the server. A payment activates a plan only after its
signature verifies and Razorpay confirms the captured amount, and activation is
idempotent, so the browser callback and the webhook can both arrive safely.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.models import STAFF, Payment, Prediction, Subscription, User, utcnow
from api.deps import audit

PERIOD_DAYS = 30
CURRENCY = "INR"


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price_paise: int
    monthly_limit: int | None
    ml: bool
    activity_log: bool
    features: tuple[str, ...]


PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free", 0, 20, False, False, (
        "Exact USP <1174> classification", "20 results per month", "Samples and result history")),
    "pro": Plan("pro", "Pro", 49900, 500, True, False, (
        "Everything in Free", "ML screening estimates (all tiers)", "500 results per month")),
    "lab": Plan("lab", "Lab", 199900, None, True, True, (
        "Everything in Pro", "Unlimited results", "Personal activity and audit log")),
}
PAID = ("pro", "lab")


class RazorpayError(RuntimeError):
    """Razorpay could not be reached or refused the request."""


class RazorpayClient:
    BASE = "https://api.razorpay.com/v1"

    def __init__(self, key_id: str, key_secret: str, timeout: float = 15):
        self.key_id = key_id
        self._secret = key_secret
        self._auth = "Basic " + base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        self._timeout = timeout

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.BASE + path, data=data, method=method)
        request.add_header("Authorization", self._auth)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise RazorpayError(f"Razorpay returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise RazorpayError("Razorpay could not be reached") from exc

    def create_order(self, amount: int, currency: str, receipt: str, notes: dict) -> dict:
        return self._call("POST", "/orders", {"amount": amount, "currency": currency,
                                              "receipt": receipt, "notes": notes})

    def fetch_payment(self, payment_id: str) -> dict:
        return self._call("GET", f"/payments/{payment_id}")

    def capture(self, payment_id: str, amount: int, currency: str) -> dict:
        return self._call("POST", f"/payments/{payment_id}/capture",
                          {"amount": amount, "currency": currency})

    def signature_valid(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(self._secret.encode(), f"{order_id}|{payment_id}".encode(),
                            hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def webhook_signature_valid(secret: str, body: bytes, signature: str) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def month_start(now: dt.datetime | None = None) -> dt.datetime:
    now = now or utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def is_staff(user: User) -> bool:
    return user.role in STAFF


def current_subscription(db: Session, user: User) -> Subscription | None:
    row = db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    return row if row and row.current_period_end > utcnow() else None


def effective_plan(db: Session, user: User) -> Plan:
    if is_staff(user):
        return PLANS["lab"]
    row = current_subscription(db, user)
    return PLANS[row.plan] if row and row.plan in PLANS else PLANS["free"]


def usage_this_month(db: Session, user: User) -> int:
    return db.scalar(select(func.count(Prediction.id)).where(
        Prediction.user_id == user.id, Prediction.created_at >= month_start())) or 0


def enforce_plan(db: Session, user: User, needs_ml: bool) -> None:
    """402 when the user's plan does not allow this classification."""
    if is_staff(user):
        return
    plan = effective_plan(db, user)
    if needs_ml and not plan.ml:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            "ML screening estimates need the Pro or Lab plan. "
                            "Exact USP classification with tapped density stays free.")
    if plan.monthly_limit is not None and usage_this_month(db, user) >= plan.monthly_limit:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            f"The {plan.name} plan allows {plan.monthly_limit} results per "
                            "month, and this month's limit is used. Upgrade for more.")


def grant_plan(db: Session, user_id: int, plan: str, days: int, source: str) -> Subscription:
    """Extend an active pass of the same plan; otherwise start a new period now."""
    now = utcnow()
    row = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
    if row is None:
        row = Subscription(user_id=user_id, plan=plan, current_period_end=now, source=source)
        db.add(row)
    start = row.current_period_end if row.plan == plan and row.current_period_end > now else now
    row.plan = plan
    row.current_period_end = start + dt.timedelta(days=days)
    row.source = source
    row.updated_at = now
    return row


def activate_payment(db: Session, client: RazorpayClient, order_id: str, payment_id: str,
                     actor: User | None, request=None) -> Payment:
    """Confirm the payment with Razorpay and grant the plan. Safe to call more than once."""
    payment = db.scalar(select(Payment).where(Payment.razorpay_order_id == order_id)
                        .with_for_update())
    if payment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown order")
    if payment.status == "paid":
        if payment.razorpay_payment_id != payment_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "This order is already paid.")
        return payment

    try:
        details = client.fetch_payment(payment_id)
        if details.get("status") == "authorized":
            details = client.capture(payment_id, payment.amount_paise, payment.currency)
    except RazorpayError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Could not confirm the payment with Razorpay. If money was "
                            "deducted, the plan activates automatically once it is confirmed."
                            ) from exc
    if (details.get("order_id") != order_id or details.get("status") != "captured"
            or int(details.get("amount", -1)) != payment.amount_paise
            or details.get("currency") != payment.currency):
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                            "The payment was not completed for the expected amount.")

    payment.status = "paid"
    payment.razorpay_payment_id = payment_id
    payment.paid_at = utcnow()
    grant_plan(db, payment.user_id, payment.plan, payment.period_days, "razorpay")
    audit(db, actor, "payment", "payment", payment.id,
          {"plan": payment.plan, "amount_paise": payment.amount_paise, "mode": payment.mode},
          request)
    db.commit()
    return payment
