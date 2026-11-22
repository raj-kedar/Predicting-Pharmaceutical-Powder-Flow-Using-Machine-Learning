"""Engine setup, schema creation and database-level integrity rules (SQLite and PostgreSQL)."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import sessionmaker

from api.db.models import Base

_PREDICTION_FROZEN = ("sample_id", "user_id", "path", "model_version", "predicted_class",
                      "acceptable", "confidence", "carr_index", "hausner", "hausner_class",
                      "criteria_agree", "inputs", "caveats", "basis", "created_at")
_SAMPLE_FROZEN = ("material_id", "operator_id", "batch_no", "replicate_no", "measured_at",
                  "sample_weight_g", "bulk_density", "tapped_density", "angle_of_repose",
                  "particle_size_um", "moisture_percent", "flow_rate_g_s", "method_ref",
                  "created_at")
_REVIEW = "reviewed_by_id, reviewed_at, review_comment"

# (name, timing, table, condition or None, message)
_RULES = [
    ("audit_no_update", "BEFORE UPDATE", "audit_log", None, "audit log is append-only"),
    ("audit_no_delete", "BEFORE DELETE", "audit_log", None, "audit log is append-only"),
    ("prediction_no_delete", "BEFORE DELETE", "predictions", None, "predictions are permanent"),
    ("sample_no_delete", "BEFORE DELETE", "samples", None, "samples are permanent"),
    ("payment_no_delete", "BEFORE DELETE", "payments", None, "payments are permanent"),
    ("prediction_frozen", f"BEFORE UPDATE OF {', '.join(_PREDICTION_FROZEN)}", "predictions",
     None, "prediction results are frozen"),
    ("prediction_single_review", f"BEFORE UPDATE OF {_REVIEW}", "predictions",
     "OLD.reviewed_at IS NOT NULL", "prediction is already reviewed"),
    ("sample_frozen", f"BEFORE UPDATE OF {', '.join(_SAMPLE_FROZEN)}", "samples", None,
     "sample measurements are frozen"),
]


def _sqlite_statements() -> list[str]:
    out = []
    for name, timing, table, condition, message in _RULES:
        when = f" WHEN {condition}" if condition else ""
        out.append(f"CREATE TRIGGER IF NOT EXISTS {name} {timing} ON {table}{when} "
                   f"BEGIN SELECT RAISE(ABORT, '{message}'); END")
    return out


def _postgres_statements() -> list[str]:
    out = ["CREATE OR REPLACE FUNCTION pf_abort() RETURNS trigger LANGUAGE plpgsql AS "
           "$$ BEGIN RAISE EXCEPTION USING MESSAGE = TG_ARGV[0]; END $$"]
    for name, timing, table, condition, message in _RULES:
        when = f" WHEN ({condition})" if condition else ""
        out.append(f"CREATE OR REPLACE TRIGGER {name} {timing} ON {table} FOR EACH ROW{when} "
                   f"EXECUTE FUNCTION pf_abort('{message}')")
    return out


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5,
                             pool_recycle=1800)

    if url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Additive only: creates missing tables and integrity triggers, never alters data."""
    Base.metadata.create_all(engine)
    dialect = engine.dialect.name
    if dialect == "postgresql":   # databases created before the superadmin role existed
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TYPE role ADD VALUE IF NOT EXISTS 'superadmin'")
    statements = (_sqlite_statements() if dialect == "sqlite"
                  else _postgres_statements() if dialect == "postgresql" else [])
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
