"""
Copy every record from a SQLite database into an empty PostgreSQL database
(for example Amazon RDS). IDs are preserved, so audit references stay valid.
The source is opened read-only and the target must be empty.

Usage (target from FLOWTOOL_DATABASE_URL):
    python -m scripts.migrate_sqlite_to_postgres data/app/flowtool.db
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from api.db.models import Base
from api.db.session import build_engine, init_db

ORDER = ["users", "materials", "samples", "predictions", "audit_log", "subscriptions",
         "payments"]


def migrate(source: Path, target_url: str) -> dict[str, int]:
    if make_url(target_url).get_backend_name() != "postgresql":
        raise SystemExit("FLOWTOOL_DATABASE_URL must point to PostgreSQL.")
    if not source.is_file():
        raise SystemExit(f"Source database not found: {source}")

    src = build_engine(f"sqlite:///{source.resolve().as_posix()}?mode=ro")
    dst = build_engine(target_url)
    init_db(dst)
    tables = Base.metadata.tables
    counts: dict[str, int] = {}
    try:
        with src.connect() as reader, dst.begin() as writer:
            if writer.scalar(select(func.count()).select_from(tables["users"])):
                raise SystemExit("Target database is not empty; refusing to overwrite.")
            source_tables = set(reader.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'").scalars())
            for name in ORDER:
                table = tables[name]
                rows = ([dict(r._mapping) for r in reader.execute(select(table))]
                        if name in source_tables else [])
                if rows:
                    writer.execute(table.insert(), rows)
                if "id" in table.c:
                    writer.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {name}), 0) + 1, false)"))
                written = writer.scalar(select(func.count()).select_from(table))
                if written != len(rows):
                    raise SystemExit(f"Row count mismatch in {name}: {len(rows)} != {written}")
                counts[name] = written
    finally:
        src.dispose()
        dst.dispose()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    target = os.environ.get("FLOWTOOL_DATABASE_URL", "")
    print("Migrated:", migrate(args.source, target))


if __name__ == "__main__":
    main()
