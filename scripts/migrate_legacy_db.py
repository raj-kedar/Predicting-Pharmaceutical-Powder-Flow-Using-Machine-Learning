"""
Copy the old flowtool.db into this project. The source is opened read-only and
an existing destination is never overwritten.

Usage: python -m scripts.migrate_legacy_db PATH_TO_OLD_DB
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from sqlalchemy.engine import make_url

from api.db.session import build_engine, init_db
from src.config import load_settings


def migrate(source: Path, destination: Path, database_url: str) -> dict[str, int]:
    if not source.is_file():
        raise SystemExit(f"Source database not found: {source}")
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing database: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    src = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
    finally:
        dst.close()

    engine = build_engine(database_url)
    init_db(engine)
    engine.dispose()

    dst = sqlite3.connect(destination)
    try:
        counts = {}
        for table in ("users", "materials", "samples", "predictions", "audit_log"):
            before = src.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            after = dst.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            if before != after:
                raise SystemExit(f"Row count mismatch in {table}: {before} != {after}")
            counts[table] = after
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("Integrity check failed on the migrated database.")
    finally:
        dst.close()
        src.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    settings = load_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        raise SystemExit("Migration target must be a SQLite file.")
    print("Migrated:", migrate(args.source, Path(url.database), settings.database_url))


if __name__ == "__main__":
    main()
