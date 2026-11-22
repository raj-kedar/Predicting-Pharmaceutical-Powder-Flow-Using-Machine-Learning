import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from api.db.models import AuditLog, Prediction, Role
from api.db.session import build_engine, init_db
from scripts.migrate_legacy_db import migrate

SAMPLE = {"material_name": "Lactose Monohydrate", "batch_no": "B1", "bulk_density": 0.5,
          "tapped_density": 0.6}


def _sample(client, headers, **changes):
    response = client.post("/samples", headers=headers, json={**SAMPLE, **changes})
    assert response.status_code == 201, response.text
    return response.json()["sample_id"]


def _predict(client, headers, **body):
    response = client.post("/classify", headers=headers,
                           json={"bulk_density": 0.5, "tapped_density": 0.6, **body})
    assert response.status_code == 200, response.text
    return response.json()


def test_health_ready_and_model_card(client):
    assert client.get("/health").json()["model_loaded"] is True
    assert client.get("/ready").json()["database"] is True
    card = client.get("/model-card").json()
    assert set(card["ml_tiers"]) == {"full", "mid", "basic"}
    assert "model" not in card["ml_tiers"]["full"]


def test_security_headers_present(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"]


def test_cors_only_allows_configured_origin(client):
    good = client.get("/health", headers={"Origin": "http://localhost:5173"})
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert good.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_oversized_body_rejected(client, analyst):
    _, headers = analyst
    response = client.post("/classify", headers=headers, content=b"x" * 70000)
    assert response.status_code == 413


def test_classify_requires_auth(client):
    assert client.post("/classify", json={"bulk_density": 0.5}).status_code == 401


def test_rule_path(client, analyst):
    _, headers = analyst
    result = _predict(client, headers)
    assert result["path"] == "rule" and result["predicted_class"] == "Fair"
    assert result["poor_flow"] is False and result["prediction_id"]


def test_ml_path(client, analyst):
    _, headers = analyst
    response = client.post("/classify", headers=headers, json={
        "bulk_density": 0.5, "angle_of_repose": 45})
    result = response.json()
    assert result["path"] == "ml" and result["poor_flow"] is True
    assert result["model_version"] == "1.1.0/basic"


@pytest.mark.parametrize("body", [
    {"bulk_density": 0.6, "tapped_density": 0.5},
    {"bulk_density": 0},
    {"bulk_density": -1, "tapped_density": 1},
    {"bulk_density": 6},
    {"bulk_density": True, "tapped_density": 1},
    {"bulk_density": 0.5},
    {"bulk_density": 0.5, "angle_of_repose": 91},
    {"bulk_density": 0.5, "tapped_densty": 0.6},
    {"bulk_density": 0.5, "angle_of_repose": 30, "moisture_percent": 101},
    {"bulk_density": 0.5, "tapped_density": 0.6, "sample_id": 2 ** 40},
])
def test_invalid_classify_inputs_are_422(client, analyst, body):
    _, headers = analyst
    assert client.post("/classify", headers=headers, json=body).status_code == 422


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_non_finite_json_is_rejected(client, analyst, literal):
    _, headers = analyst
    raw = ('{"bulk_density":0.5,"angle_of_repose":30,"particle_size_um":%s}' % literal).encode()
    response = client.post("/classify", content=raw,
                           headers={**headers, "Content-Type": "application/json"})
    assert response.status_code == 422


def test_unknown_sample_is_404(client, analyst):
    _, headers = analyst
    response = client.post("/classify", headers=headers, json={
        "bulk_density": 0.5, "tapped_density": 0.6, "sample_id": 999})
    assert response.status_code == 404


def test_inputs_must_match_linked_sample(client, analyst):
    _, headers = analyst
    sample_id = _sample(client, headers)
    response = client.post("/classify", headers=headers, json={
        "bulk_density": 0.4, "tapped_density": 0.6, "sample_id": sample_id})
    assert response.status_code == 409 and "bulk_density" in response.json()["detail"]
    assert _predict(client, headers, sample_id=sample_id)["path"] == "rule"


def test_classify_recorded_sample(client, analyst):
    _, headers = analyst
    sample_id = _sample(client, headers)
    response = client.post(f"/samples/{sample_id}/classify", headers=headers)
    assert response.status_code == 200 and response.json()["carr_index"] == 16.67


def test_duplicate_sample_is_409_and_leaves_no_partial_data(client, analyst):
    _, headers = analyst
    _sample(client, headers)
    response = client.post("/samples", headers=headers, json={
        **SAMPLE, "material_name": "  lactose   MONOHYDRATE "})
    assert response.status_code == 409
    assert len(client.get("/materials", headers=headers).json()) == 1


@pytest.mark.parametrize("change", [{"replicate_no": 0}, {"sample_weight_g": -1},
                                    {"moisture_percent": 150}, {"particle_size_um": -5},
                                    {"material_name": "   "}, {"batch_no": ""},
                                    {"batch_no": "x" * 65}, {"tapped_density": 0.4}])
def test_invalid_samples_rejected(client, analyst, change):
    _, headers = analyst
    assert client.post("/samples", headers=headers, json={**SAMPLE, **change}).status_code == 422


def test_analysts_cannot_see_each_others_records(client, make_user):
    _, first = make_user(Role.analyst, "one@example.com")
    _, second = make_user(Role.analyst, "two@example.com")
    sample_id = _sample(client, first)
    prediction_id = _predict(client, first)["prediction_id"]
    assert client.get(f"/samples/{sample_id}", headers=second).status_code == 404
    assert client.post(f"/samples/{sample_id}/classify", headers=second).status_code == 404
    assert client.post(f"/samples/{sample_id}/void", headers=second,
                       json={"reason": "not mine"}).status_code == 404
    assert client.get(f"/predictions/{prediction_id}", headers=second).status_code == 404
    assert client.get("/predictions", headers=second).json() == []
    assert client.get("/samples", headers=second).json() == []


def test_void_workflow(client, analyst, reviewer):
    _, headers = analyst
    _, reviewer_headers = reviewer
    sample_id = _sample(client, headers)
    prediction_id = _predict(client, headers, sample_id=sample_id)["prediction_id"]
    assert client.post(f"/samples/{sample_id}/void", headers=headers,
                       json={"reason": "  "}).status_code == 422
    assert client.post(f"/samples/{sample_id}/void", headers=headers,
                       json={"reason": "spilled"}).status_code == 200
    assert client.post(f"/samples/{sample_id}/void", headers=headers,
                       json={"reason": "again"}).status_code == 409
    assert client.post(f"/samples/{sample_id}/classify", headers=headers).status_code == 409
    assert client.post(f"/predictions/{prediction_id}/review",
                       headers=reviewer_headers).status_code == 409
    assert client.get("/samples", headers=headers).json() == []
    assert len(client.get("/samples?include_voided=true", headers=headers).json()) == 1
    assert client.get(f"/predictions/{prediction_id}", headers=headers) \
        .json()["sample_voided"] is True


def test_review_rules(client, analyst, reviewer, make_user):
    _, headers = analyst
    _, reviewer_headers = reviewer
    prediction_id = _predict(client, headers)["prediction_id"]
    assert client.post(f"/predictions/{prediction_id}/review", headers=headers).status_code == 403
    own = _predict(client, reviewer_headers)["prediction_id"]
    assert client.post(f"/predictions/{own}/review", headers=reviewer_headers).status_code == 403
    done = client.post(f"/predictions/{prediction_id}/review", headers=reviewer_headers,
                       json={"comment": "checked"})
    assert done.status_code == 200 and done.json()["reviewed_at"].endswith("+00:00")
    _, second = make_user(Role.reviewer, "second-reviewer@example.com")
    assert client.post(f"/predictions/{prediction_id}/review", headers=second,
                       json={"comment": "overwrite"}).status_code == 409
    detail = client.get(f"/predictions/{prediction_id}", headers=headers).json()
    assert detail["review_comment"] == "checked"


@pytest.mark.parametrize("query", ["limit=-1", "limit=0", "limit=201", "offset=-1",
                                   "limit=abc", "path=wrong"])
def test_pagination_is_bounded(client, analyst, query):
    _, headers = analyst
    assert client.get(f"/predictions?{query}", headers=headers).status_code == 422


def test_pagination_and_filters(client, analyst, reviewer):
    _, headers = analyst
    _, reviewer_headers = reviewer
    ids = [_predict(client, headers)["prediction_id"] for _ in range(3)]
    assert [r["id"] for r in client.get("/predictions?limit=2", headers=headers).json()] \
        == ids[:0:-1]
    client.post(f"/predictions/{ids[0]}/review", headers=reviewer_headers)
    assert [r["id"] for r in client.get("/predictions?reviewed=true", headers=headers).json()] \
        == [ids[0]]


@pytest.mark.parametrize("url", ["/predictions/99999999999999999999", "/predictions/0",
                                 "/samples/99999999999999999999"])
def test_huge_ids_are_422_not_500(client, analyst, url):
    _, headers = analyst
    assert client.get(url, headers=headers).status_code == 422


def test_audit_records_actions(client, admin, analyst):
    _, admin_headers = admin
    user, headers = analyst
    _predict(client, headers)
    rows = client.get("/audit?action=classify", headers=admin_headers).json()
    assert len(rows) == 1 and rows[0]["actor"] == user.email
    assert client.get("/audit?limit=-1", headers=admin_headers).status_code == 422


def test_orm_blocks_audit_changes(client, analyst, db):
    _, headers = analyst
    _predict(client, headers)
    entry = db.query(AuditLog).first()
    entry.action = "tampered"
    with pytest.raises(ValueError):
        db.commit()
    db.rollback()


@pytest.mark.parametrize("statement", [
    "UPDATE audit_log SET action='x'", "DELETE FROM audit_log",
    "DELETE FROM predictions", "UPDATE predictions SET predicted_class='Excellent'",
])
def test_database_blocks_tampering_even_outside_the_api(client, analyst, app, statement):
    _, headers = analyst
    _predict(client, headers)
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as connection:
            connection.execute(text(statement))


def test_database_allows_only_one_review(client, analyst, reviewer, app, db):
    _, headers = analyst
    _, reviewer_headers = reviewer
    prediction_id = _predict(client, headers)["prediction_id"]
    client.post(f"/predictions/{prediction_id}/review", headers=reviewer_headers)
    with pytest.raises(DBAPIError):
        with app.state.engine.begin() as connection:
            connection.execute(text("UPDATE predictions SET review_comment='changed'"))
    assert db.get(Prediction, prediction_id).review_comment == ""


def test_unhandled_error_hides_details(app, client, analyst, monkeypatch):
    _, headers = analyst
    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr("api.classification.classify", boom)
    response = client.post("/classify", headers=headers,
                           json={"bulk_density": 0.5, "tapped_density": 0.6})
    assert response.status_code == 500
    assert "secret" not in response.text and response.json()["request_id"]


def test_failed_save_leaves_no_orphan_audit(client, analyst, db, monkeypatch):
    _, headers = analyst
    before = db.query(AuditLog).count()
    monkeypatch.setattr("api.classification.audit",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")))
    assert client.post("/classify", headers=headers, json={
        "bulk_density": 0.5, "tapped_density": 0.6}).status_code == 500
    db.expire_all()
    assert db.query(AuditLog).count() == before and db.query(Prediction).count() == 0


def test_startup_fails_without_secret(settings):
    import dataclasses

    from fastapi.testclient import TestClient

    from api.main import create_app
    from src.config import ConfigError
    with pytest.raises(ConfigError):
        with TestClient(create_app(dataclasses.replace(settings, secret_key="short"))):
            pass


def test_migration_preserves_rows_and_refuses_overwrite(tmp_path):
    source = tmp_path / "old.db"
    legacy_url = f"sqlite:///{source.as_posix()}"
    engine = build_engine(legacy_url)
    init_db(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users (email, full_name, password_hash, role, is_active, created_at) "
            "VALUES ('a@b.co', 'A', 'h', 'admin', 1, '2026-11-20 10:00:00.000000')"))
    engine.dispose()

    target = tmp_path / "new" / "flowtool.db"
    counts = migrate(source, target, f"sqlite:///{target.as_posix()}")
    assert counts["users"] == 1
    with sqlite3.connect(target) as connection:
        triggers = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
    assert triggers >= 7
    with pytest.raises(SystemExit):
        migrate(source, target, f"sqlite:///{target.as_posix()}")
