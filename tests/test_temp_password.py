import sys

import pytest

from api.db.models import PasswordChangeRequired, Role, User
from scripts import make_superadmin

TEMP = "Temp@1234"


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def promoted(settings, db, make_user, monkeypatch):
    user, _ = make_user(Role.admin, "admin@flowtool.local")
    monkeypatch.setattr(make_superadmin, "load_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["x", "admin@flowtool.local", "--new-email",
                                      "owner@example.com", "--temporary-password", TEMP])
    make_superadmin.main()
    db.expire_all()
    return user


def test_temporary_password_must_be_changed_first(client, promoted, db):
    assert db.get(User, promoted.id).role == Role.superadmin
    assert db.get(PasswordChangeRequired, promoted.id) is not None
    response = _login(client, "owner@example.com", TEMP)
    assert response.status_code == 200 and response.json()["must_change_password"] is True
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=headers).json()["must_change_password"] is True
    for path in ("/users", "/admin/overview", "/predictions", "/site/content"):
        if path == "/site/content":
            assert client.get(path).status_code == 200          # public pages still work
        else:
            blocked = client.get(path, headers=headers)
            assert blocked.status_code == 403 and "temporary password" in blocked.json()["detail"]
    assert client.post("/auth/change-password", headers=headers, json={
        "current_password": TEMP, "new_password": TEMP}).status_code == 422
    changed = client.post("/auth/change-password", headers=headers, json={
        "current_password": TEMP, "new_password": "my-own-strong-password"})
    assert changed.status_code == 200 and changed.json()["must_change_password"] is False
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/admin/overview", headers=fresh).status_code == 200
    assert _login(client, "owner@example.com", TEMP).status_code == 401


def test_password_not_logged(client, promoted, db):
    from api.db.models import AuditLog
    details = [row.detail for row in db.query(AuditLog).all()]
    assert TEMP not in str(details)


def test_temporary_password_too_short(settings, make_user, monkeypatch):
    make_user(Role.admin, "a@example.com")
    monkeypatch.setattr(make_superadmin, "load_settings", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["x", "a@example.com", "--temporary-password", "short"])
    with pytest.raises(SystemExit):
        make_superadmin.main()


def test_admin_set_passwords_are_temporary(client, admin, analyst):
    _, admin_h = admin
    user, _ = analyst
    created = client.post("/users", headers=admin_h, json={
        "email": "new@example.com", "full_name": "New User", "password": "given-by-admin"})
    assert created.status_code == 201
    first = _login(client, "new@example.com", "given-by-admin").json()
    assert first["must_change_password"] is True
    client.patch(f"/users/{user.id}", headers=admin_h, json={"password": "reset-by-admin"})
    assert _login(client, user.email, "reset-by-admin").json()["must_change_password"] is True


def test_self_registered_users_are_not_forced(client):
    response = client.post("/auth/register", json={"email": "self@example.com", "full_name": "Self",
                                                    "password": "my-own-password"})
    assert response.json()["must_change_password"] is False
