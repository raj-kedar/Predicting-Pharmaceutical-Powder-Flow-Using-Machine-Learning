import base64
import json
import time

import pytest

from api.db.models import AuditLog, Role, User
from api.security import create_token, decode_token, hash_password, verify_password
from tests.conftest import PASSWORD

SECRET = "s" * 40


def test_password_round_trip():
    stored = hash_password("a-good-password")
    assert verify_password("a-good-password", stored)
    assert not verify_password("wrong-password", stored)
    assert not verify_password("x", "garbage")


def _token(ttl=60):
    return create_token(SECRET, 1, "a@b.co", "admin", "hash", ttl)


def test_token_round_trip():
    assert decode_token(SECRET, _token())["sub"] == 1


@pytest.mark.parametrize("bad", ["", "a", "a.b", "a.b.c", "a.b.c.d", "é.é.é", "!!!.???.***",
                                 "x" * 5000])
def test_malformed_tokens_return_none(bad):
    assert decode_token(SECRET, bad) is None


def test_expired_wrong_key_and_tampered_tokens():
    assert decode_token(SECRET, _token(-1)) is None
    assert decode_token("k" * 40, _token()) is None
    head, payload, sig = _token().split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["role"] = "admin"
    claims["sub"] = "2"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    assert decode_token(SECRET, f"{head}.{forged}.{sig}") is None


@pytest.mark.parametrize("header", ["Bearer a.b.c", "Bearer é.é.é", "Bearer !!!", "Basic abc"])
def test_bad_tokens_get_401_not_500(client, header):
    assert client.get("/auth/me", headers={"Authorization": header.encode("utf-8")}) \
        .status_code == 401


def test_login_success_and_me(client, make_user):
    user, _ = make_user(Role.analyst, "person@example.com")
    response = client.post("/auth/login", json={"email": " PERSON@example.com ",
                                                "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["id"] == user.id


def test_failure_message_does_not_reveal_accounts(client, make_user):
    make_user(Role.analyst, "real@example.com")
    known = client.post("/auth/login", json={"email": "real@example.com", "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()


def test_lockout_then_correct_password_blocked(client, make_user):
    make_user(Role.analyst, "lock@example.com")
    for _ in range(3):
        assert client.post("/auth/login", json={"email": "lock@example.com",
                                                "password": "wrong"}).status_code == 401
    blocked = client.post("/auth/login", json={"email": "lock@example.com", "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0


def test_success_resets_failure_count(client, make_user):
    make_user(Role.analyst, "reset@example.com")
    for _ in range(2):
        client.post("/auth/login", json={"email": "reset@example.com", "password": "wrong"})
    assert client.post("/auth/login", json={"email": "reset@example.com",
                                            "password": PASSWORD}).status_code == 200
    for _ in range(2):
        assert client.post("/auth/login", json={"email": "reset@example.com",
                                                "password": "wrong"}).status_code == 401


def test_inactive_user_cannot_login_or_use_token(client, make_user):
    _, headers = make_user(Role.analyst, "off@example.com", active=False)
    assert client.post("/auth/login", json={"email": "off@example.com",
                                            "password": PASSWORD}).status_code == 401
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_change_password_revokes_old_token(client, analyst):
    user, headers = analyst
    response = client.post("/auth/change-password", headers=headers, json={
        "current_password": PASSWORD, "new_password": "brand-new-password"})
    assert response.status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=fresh).status_code == 200
    assert client.post("/auth/login", json={"email": user.email, "password": PASSWORD}) \
        .status_code == 401


def test_change_password_needs_current(client, analyst):
    _, headers = analyst
    assert client.post("/auth/change-password", headers=headers, json={
        "current_password": "wrong", "new_password": "brand-new-password"}).status_code == 401


def test_validation_errors_never_echo_passwords(client, admin):
    _, headers = admin
    response = client.post("/users", headers=headers, json={
        "email": "new@example.com", "full_name": "New", "password": "short"})
    assert response.status_code == 422 and "short" not in json.dumps(
        [e.get("input") for e in response.json()["detail"]])
    assert "input" not in response.json()["detail"][0]


def test_lone_surrogate_password_is_not_a_500(client):
    raw = b'{"email":"a@example.com","password":"\\ud800abcdefgh"}'
    response = client.post("/auth/login", content=raw,
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422


@pytest.mark.parametrize("method,url", [("get", "/users"), ("get", "/audit"),
                                        ("post", "/users"), ("patch", "/users/1")])
def test_admin_routes_reject_analyst(client, analyst, method, url):
    _, headers = analyst
    kwargs = {"json": {"full_name": "Xx"}} if method == "patch" else {}
    if url == "/users" and method == "post":
        kwargs = {"json": {"email": "x@example.com", "full_name": "Xx", "password": "password1"}}
    assert getattr(client, method)(url, headers=headers, **kwargs).status_code == 403


def test_duplicate_email_is_409(client, admin):
    _, headers = admin
    body = {"email": "dup@example.com", "full_name": "Dup", "password": "password123"}
    assert client.post("/users", headers=headers, json=body).status_code == 201
    body["email"] = "DUP@example.com"
    assert client.post("/users", headers=headers, json=body).status_code == 409


def test_last_admin_cannot_be_removed(client, admin, make_user):
    user, headers = admin
    assert client.patch(f"/users/{user.id}", headers=headers,
                        json={"is_active": False}).status_code == 409
    assert client.patch(f"/users/{user.id}", headers=headers,
                        json={"role": "analyst"}).status_code == 409
    make_user(Role.admin, "second@example.com")
    assert client.patch(f"/users/{user.id}", headers=headers,
                        json={"role": "analyst"}).status_code == 200


def test_role_change_takes_effect_on_existing_token(client, admin, analyst):
    _, admin_headers = admin
    user, headers = analyst
    assert client.get("/users", headers=headers).status_code == 403
    client.patch(f"/users/{user.id}", headers=admin_headers, json={"role": "admin"})
    assert client.get("/users", headers=headers).status_code == 200


def test_patch_rejects_null_and_empty(client, admin, analyst):
    _, headers = admin
    user, _ = analyst
    assert client.patch(f"/users/{user.id}", headers=headers, json={}).status_code == 422
    assert client.patch(f"/users/{user.id}", headers=headers,
                        json={"role": None}).status_code == 422


def test_admin_password_reset_not_logged_in_audit(client, admin, analyst, db):
    _, headers = admin
    user, user_headers = analyst
    assert client.patch(f"/users/{user.id}", headers=headers,
                        json={"password": "admin-set-password"}).status_code == 200
    assert client.get("/auth/me", headers=user_headers).status_code == 401
    entries = db.query(AuditLog).filter(AuditLog.action == "update").all()
    assert entries and "admin-set-password" not in json.dumps([e.detail for e in entries])


def test_token_timing_field_is_integer():
    assert decode_token(SECRET, _token())["exp"] > time.time()


def test_user_model_has_no_password_in_response(client, admin):
    _, headers = admin
    rows = client.get("/users", headers=headers).json()
    leaked = {"password", "password_hash"}
    assert rows and all(not leaked & row.keys() for row in rows)
    assert all("scrypt$" not in str(value) for row in rows for value in row.values())
    assert User.__tablename__ == "users"
