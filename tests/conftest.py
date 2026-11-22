"""Fixtures. Every test gets its own temporary database; real data is never touched."""
import dataclasses
import datetime as dt
import os
import pickle

os.environ["APP_ENV"] = "testing"
os.environ["FLOWTOOL_SECRET_KEY"] = "test-secret-key-that-is-long-enough-000000"

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.db.models import Role, Subscription, User, utcnow  # noqa: E402
from api.main import create_app  # noqa: E402
from api.security import create_token, hash_password  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.models.forest import Forest  # noqa: E402
from src.models.registry import FEATURES, tier_path, write_manifest  # noqa: E402
from src.models.train import CLASSES, TIER_FEATURES  # noqa: E402

PASSWORD = "correct-horse-battery"
VERSION = "1.1.0"


@pytest.fixture(scope="session")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    """Small models trained on generated data, so tests do not need the lab dataset."""
    directory = tmp_path_factory.mktemp("models")
    rng = np.random.default_rng(0)
    n = 200
    frame = pd.DataFrame({
        "Bulk_Density_g_mL": rng.uniform(0.2, 0.8, n),
        "Angle_of_Repose_deg": rng.uniform(25, 48, n),
        "Mean_Particle_Size_um": rng.uniform(55, 165, n),
        "Moisture_Content_percent": rng.uniform(0.9, 6.1, n),
        "Flow_Rate_g_s": rng.uniform(1, 7.7, n),
    })[FEATURES]
    y = (frame["Angle_of_Repose_deg"].values > 36).astype(int)
    for tier, features in TIER_FEATURES.items():
        bundle = {
            "version": VERSION, "tier": tier, "features": features, "classes": CLASSES,
            "model": Forest(n=5, max_depth=3, seed=1).fit(frame[features].values, y, 2),
            "lomo_accuracy": 0.9, "lomo_balanced_acc": 0.9, "majority_baseline": 0.5,
            "n_materials": 10, "basis": "test model",
        }
        with open(tier_path(directory, tier, VERSION), "wb") as fh:
            pickle.dump(bundle, fh)
    write_manifest(directory, VERSION, frame)
    return directory


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


def _reset_postgres(url: str) -> None:
    from sqlalchemy import create_engine
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    engine.dispose()


@pytest.fixture
def settings(tmp_path, model_dir):
    """SQLite by default; set TEST_DATABASE_URL to run the whole suite on PostgreSQL."""
    if TEST_DATABASE_URL:
        _reset_postgres(TEST_DATABASE_URL)
        url = TEST_DATABASE_URL
    else:
        url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    return dataclasses.replace(load_settings("testing"), database_url=url, model_dir=model_dir,
                               upload_dir=tmp_path / "uploads", s3_bucket="")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def db(app, client):
    session = app.state.session_factory()
    yield session
    session.close()
    app.state.engine.dispose()


@pytest.fixture
def make_user(db, settings, password_hash):
    def _make(role=Role.analyst, email=None, active=True, plan="lab"):
        """Analysts get the Lab plan unless a test asks for another, so limits stay out of the way."""
        email = email or f"{role.value}{db.query(User).count()}@example.com"
        user = User(email=email, full_name=f"Test {role.value}", role=role,
                    password_hash=password_hash, is_active=active)
        db.add(user)
        db.flush()
        if role == Role.analyst and plan != "free":
            db.add(Subscription(user_id=user.id, plan=plan, source="admin",
                                current_period_end=utcnow() + dt.timedelta(days=30)))
        db.commit()
        token = create_token(settings.secret_key, user.id, user.email, role.value,
                             user.password_hash, 3600)
        return user, {"Authorization": f"Bearer {token}"}
    return _make


@pytest.fixture
def analyst(make_user):
    return make_user(Role.analyst)


@pytest.fixture
def reviewer(make_user):
    return make_user(Role.reviewer)


@pytest.fixture
def admin(make_user):
    return make_user(Role.admin)
