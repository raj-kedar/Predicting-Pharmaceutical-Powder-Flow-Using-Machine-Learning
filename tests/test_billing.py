import dataclasses
import datetime as dt
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.billing import RazorpayClient, RazorpayError
from api.db.models import EnginePath, Payment, Prediction, Role, Subscription, utcnow
from api.main import create_app

SECRET = "test_key_secret_value"
WEBHOOK_SECRET = "test_webhook_secret_value"
EXACT = {"bulk_density": 0.5, "tapped_density": 0.6}
ESTIMATE = {"bulk_density": 0.5, "angle_of_repose": 35}


class FakeRazorpay(RazorpayClient):
    """Real signature code; network calls replaced with an in-memory Razorpay."""

    def __init__(self):
        super().__init__("rzp_test_fake", SECRET)
        self.orders, self.payments, self.captured, self.fail = {}, {}, [], False

    def _call(self, method, path, body=None):
        if self.fail:
            raise RazorpayError("down")
        if path == "/orders":
            order_id = f"order_{len(self.orders) + 1:06d}"
            self.orders[order_id] = body
            return {"id": order_id, **body}
        payment_id = path.split("/")[2]
        if path.endswith("/capture"):
            self.captured.append(payment_id)
            self.payments[payment_id]["status"] = "captured"
        return dict(self.payments[payment_id])

    def pay(self, order_id, payment_id, amount=None, status="captured"):
        order = self.orders[order_id]
        self.payments[payment_id] = {"id": payment_id, "order_id": order_id, "status": status,
                                     "amount": order["amount"] if amount is None else amount,
                                     "currency": order["currency"]}
        signature = hmac.new(SECRET.encode(), f"{order_id}|{payment_id}".encode(),
                             hashlib.sha256).hexdigest()
        return {"razorpay_order_id": order_id, "razorpay_payment_id": payment_id,
                "razorpay_signature": signature}


@pytest.fixture
def rzp():
    return FakeRazorpay()


@pytest.fixture
def billing_app(settings, rzp):
    app = create_app(dataclasses.replace(settings, razorpay_key_id="rzp_test_fake",
                                         razorpay_key_secret=SECRET,
                                         razorpay_webhook_secret=WEBHOOK_SECRET))
    app.state.razorpay = rzp
    return app


@pytest.fixture
def bclient(billing_app):
    with TestClient(billing_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def bdb(billing_app, bclient):
    session = billing_app.state.session_factory()
    yield session
    session.close()
    billing_app.state.engine.dispose()


@pytest.fixture
def buyer(bdb, settings, password_hash):
    from api.db.models import User
    from api.security import create_token
    user = User(email="buyer@example.com", full_name="Buyer", role=Role.analyst,
                password_hash=password_hash)
    bdb.add(user)
    bdb.commit()
    token = create_token(settings.secret_key, user.id, user.email, "analyst", user.password_hash, 3600)
    return user, {"Authorization": f"Bearer {token}"}


def _order(client, headers, plan="pro"):
    response = client.post("/billing/orders", headers=headers, json={"plan": plan})
    assert response.status_code == 200, response.text
    return response.json()


def test_plans_are_public_and_priced_on_server(client):
    body = client.get("/billing/plans").json()
    assert [p["code"] for p in body["plans"]] == ["free", "pro", "lab"]
    assert [p["price_paise"] for p in body["plans"]] == [0, 49900, 199900]
    assert body["mode"] == "disabled" and body["key_id"] is None


def test_orders_unavailable_without_keys(client, make_user):
    _, headers = make_user(Role.analyst, plan="free")
    assert client.post("/billing/orders", headers=headers, json={"plan": "pro"}).status_code == 503


def test_free_plan_blocks_ml_but_allows_exact(client, make_user):
    _, headers = make_user(Role.analyst, plan="free")
    assert client.post("/classify", headers=headers, json=EXACT).status_code == 200
    blocked = client.post("/classify", headers=headers, json=ESTIMATE)
    assert blocked.status_code == 402 and "Pro" in blocked.json()["detail"]
    me = client.get("/billing/me", headers=headers).json()
    assert me["plan"] == "free" and me["used_this_month"] == 1 and me["monthly_limit"] == 20


def test_free_monthly_limit(client, make_user, db):
    user, headers = make_user(Role.analyst, plan="free")
    for _ in range(20):
        db.add(Prediction(user_id=user.id, path=EnginePath.rule, predicted_class="Good",
                          inputs={}, created_at=utcnow()))
    db.add(Prediction(user_id=user.id, path=EnginePath.rule, predicted_class="Good", inputs={},
                      created_at=utcnow() - dt.timedelta(days=40)))
    db.commit()
    response = client.post("/classify", headers=headers, json=EXACT)
    assert response.status_code == 402 and "20 results" in response.json()["detail"]


def test_staff_are_never_limited(client, reviewer):
    _, headers = reviewer
    assert client.post("/classify", headers=headers, json=ESTIMATE).status_code == 200
    assert client.get("/billing/me", headers=headers).json()["staff"] is True


def test_expired_subscription_falls_back_to_free(client, make_user, db):
    user, headers = make_user(Role.analyst, plan="pro")
    row = db.query(Subscription).filter_by(user_id=user.id).one()
    row.current_period_end = utcnow() - dt.timedelta(seconds=1)
    db.commit()
    assert client.post("/classify", headers=headers, json=ESTIMATE).status_code == 402


def test_full_payment_flow_activates_pro(bclient, buyer, rzp, bdb):
    _, headers = buyer
    order = _order(bclient, headers)
    assert order["amount"] == 49900 and order["currency"] == "INR"
    assert rzp.orders[order["order_id"]]["amount"] == 49900
    response = bclient.post("/billing/verify", headers=headers, json=rzp.pay(order["order_id"], "pay_000001"))
    assert response.status_code == 200 and response.json()["plan"] == "pro"
    end = dt.datetime.fromisoformat(response.json()["current_period_end"])
    assert dt.timedelta(days=29) < end - utcnow() <= dt.timedelta(days=30)
    assert bclient.post("/classify", headers=headers, json=ESTIMATE).status_code == 200
    again = bclient.post("/billing/verify", headers=headers, json=rzp.pay(order["order_id"], "pay_000001"))
    assert again.status_code == 200
    assert bdb.query(Payment).filter_by(status="paid").count() == 1


def test_second_purchase_extends_period(bclient, buyer, rzp):
    _, headers = buyer
    for number in (1, 2):
        order = _order(bclient, headers)
        result = bclient.post("/billing/verify", headers=headers,
                              json=rzp.pay(order["order_id"], f"pay_00000{number}")).json()
    end = dt.datetime.fromisoformat(result["current_period_end"])
    assert end - utcnow() > dt.timedelta(days=59)


def test_authorized_payment_is_captured(bclient, buyer, rzp):
    _, headers = buyer
    order = _order(bclient, headers, "lab")
    body = rzp.pay(order["order_id"], "pay_auth01", status="authorized")
    assert bclient.post("/billing/verify", headers=headers, json=body).json()["plan"] == "lab"
    assert rzp.captured == ["pay_auth01"]


def test_forged_signature_rejected(bclient, buyer, rzp):
    _, headers = buyer
    order = _order(bclient, headers)
    body = rzp.pay(order["order_id"], "pay_forged")
    body["razorpay_signature"] = "0" * 64
    assert bclient.post("/billing/verify", headers=headers, json=body).status_code == 400
    assert bclient.get("/billing/me", headers=headers).json()["plan"] == "free"


@pytest.mark.parametrize("kwargs", [{"amount": 100}, {"status": "failed"}])
def test_wrong_amount_or_unpaid_not_activated(bclient, buyer, rzp, kwargs):
    _, headers = buyer
    order = _order(bclient, headers)
    body = rzp.pay(order["order_id"], "pay_bad001", **kwargs)
    assert bclient.post("/billing/verify", headers=headers, json=body).status_code == 402
    assert bclient.get("/billing/me", headers=headers).json()["plan"] == "free"


def test_cannot_verify_someone_elses_order(bclient, buyer, rzp, make_user):
    _, headers = buyer
    order = _order(bclient, headers)
    other = make_user(Role.analyst, "other@example.com", plan="free")[1]
    assert bclient.post("/billing/verify", headers=other,
                        json=rzp.pay(order["order_id"], "pay_other1")).status_code == 404


def test_one_payment_cannot_pay_two_orders(bclient, buyer, rzp):
    _, headers = buyer
    first, second = _order(bclient, headers), _order(bclient, headers)
    assert bclient.post("/billing/verify", headers=headers,
                        json=rzp.pay(first["order_id"], "pay_shared")).status_code == 200
    reused = rzp.pay(second["order_id"], "pay_shared")
    assert bclient.post("/billing/verify", headers=headers, json=reused).status_code == 409


def test_client_cannot_set_price(bclient, buyer):
    _, headers = buyer
    assert bclient.post("/billing/orders", headers=headers,
                        json={"plan": "pro", "amount": 1}).status_code == 422
    assert bclient.post("/billing/orders", headers=headers, json={"plan": "free"}).status_code == 422


def test_razorpay_outage_is_502(bclient, buyer, rzp):
    _, headers = buyer
    rzp.fail = True
    assert bclient.post("/billing/orders", headers=headers, json={"plan": "pro"}).status_code == 502


def _webhook(client, payload, secret=WEBHOOK_SECRET):
    raw = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/billing/webhook", content=raw,
                       headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature})


def test_webhook_activates_and_is_idempotent(bclient, buyer, rzp, bdb):
    _, headers = buyer
    order = _order(bclient, headers)
    rzp.pay(order["order_id"], "pay_hook01")
    event = {"event": "payment.captured",
             "payload": {"payment": {"entity": {"id": "pay_hook01", "order_id": order["order_id"]}}}}
    assert _webhook(bclient, event, "wrong-secret").status_code == 400
    assert _webhook(bclient, event).status_code == 200
    assert _webhook(bclient, event).status_code == 200
    assert bclient.get("/billing/me", headers=headers).json()["plan"] == "pro"
    assert bdb.query(Payment).filter_by(status="paid").count() == 1


def test_payments_cannot_be_deleted(bclient, buyer, rzp, billing_app):
    _, headers = buyer
    _order(bclient, headers)
    with pytest.raises(DBAPIError):
        with billing_app.state.engine.begin() as connection:
            connection.execute(text("DELETE FROM payments"))


def test_register_creates_free_analyst(client):
    response = client.post("/auth/register", json={"email": "New@Example.com", "full_name": " New  User ",
                                                    "password": "a-strong-password"})
    assert response.status_code == 201
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    me = client.get("/auth/me", headers=headers).json()
    assert me["role"] == "analyst" and me["email"] == "new@example.com" and me["full_name"] == "New User"
    assert client.get("/billing/me", headers=headers).json()["plan"] == "free"
    duplicate = client.post("/auth/register", json={"email": "new@example.com", "full_name": "Again",
                                                     "password": "a-strong-password"})
    assert duplicate.status_code == 409


def test_register_cannot_choose_role(client):
    response = client.post("/auth/register", json={"email": "x@example.com", "full_name": "X Y",
                                                    "password": "a-strong-password", "role": "admin"})
    assert response.status_code == 422


def test_register_rate_limited(client):
    codes = [client.post("/auth/register", json={"email": f"u{i}@example.com", "full_name": "User",
                                                 "password": "a-strong-password"}).status_code
             for i in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429


def test_register_can_be_disabled(settings):
    with TestClient(create_app(dataclasses.replace(settings, allow_registration=False))) as client:
        assert client.post("/auth/register", json={"email": "a@example.com", "full_name": "A B",
                                                   "password": "a-strong-password"}).status_code == 403


def test_admin_overview_and_plan_grants(client, admin, make_user):
    _, admin_headers = admin
    user, headers = make_user(Role.analyst, plan="free")
    assert client.get("/admin/overview", headers=headers).status_code == 403
    granted = client.post(f"/admin/users/{user.id}/plan", headers=admin_headers, json={"plan": "pro", "days": 7})
    assert granted.status_code == 200
    assert client.get("/billing/me", headers=headers).json()["plan"] == "pro"
    overview = client.get("/admin/overview", headers=admin_headers).json()
    assert overview["active_subscriptions"]["pro"] == 1 and overview["users"]["admin"] == 1
    subs = client.get("/admin/subscriptions", headers=admin_headers).json()
    assert any(s["user_id"] == user.id and s["active"] for s in subs)
    assert client.post(f"/admin/users/{user.id}/plan", headers=admin_headers,
                       json={"plan": "free"}).status_code == 200
    assert client.get("/billing/me", headers=headers).json()["plan"] == "free"
    assert client.post("/admin/users/999/plan", headers=admin_headers, json={"plan": "pro"}).status_code == 404
    assert client.post(f"/admin/users/{user.id}/plan", headers=admin_headers,
                       json={"plan": "pro", "days": 0}).status_code == 422


def test_admin_payments_list(bclient, buyer, rzp, billing_app, bdb, password_hash, settings):
    from api.db.models import User
    from api.security import create_token
    _, headers = buyer
    order = _order(bclient, headers)
    bclient.post("/billing/verify", headers=headers, json=rzp.pay(order["order_id"], "pay_list01"))
    boss = User(email="boss@example.com", full_name="Boss", role=Role.admin, password_hash=password_hash)
    bdb.add(boss)
    bdb.commit()
    token = create_token(settings.secret_key, boss.id, boss.email, "admin", boss.password_hash, 3600)
    rows = bclient.get("/admin/payments", headers={"Authorization": f"Bearer {token}"}).json()
    assert rows[0]["status"] == "paid" and rows[0]["amount_paise"] == 49900 and rows[0]["mode"] == "test"
    overview = bclient.get("/admin/overview", headers={"Authorization": f"Bearer {token}"}).json()
    assert overview["revenue_paise"]["test"] == 49900 and overview["revenue_paise"]["live"] == 0
