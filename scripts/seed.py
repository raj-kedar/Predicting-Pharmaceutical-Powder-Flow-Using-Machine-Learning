"""
First-time setup: create a signing key in .env (if none) and any missing starter
users. Generated passwords are printed once and stored only as hashes.

Usage: python -m scripts.seed
"""
from __future__ import annotations

import os
import secrets

from dotenv import dotenv_values

from api.db.models import Material, PasswordChangeRequired, Role, User
from api.db.session import build_engine, build_session_factory, init_db
from api.security import generate_secret, hash_password
from src.config import MIN_SECRET_LENGTH, ROOT, load_settings

# The real sign-in email is a private server setting, so it is never published with the code.
SUPERADMIN_EMAIL = (os.environ.get("FLOWTOOL_SUPERADMIN_EMAIL") or "superadmin@flowlytix.local").strip().lower()
SEED_USERS = [(SUPERADMIN_EMAIL, "FlowLytix Superadmin", Role.superadmin),
              ("reviewer@flowtool.local", "QA Reviewer", Role.reviewer),
              ("analyst@flowtool.local", "Lab Analyst", Role.analyst)]
MATERIALS = [("Microcrystalline Cellulose PH102", "Excipient"),
             ("Lactose Monohydrate", "Excipient"), ("Magnesium Stearate", "Excipient"),
             ("Metformin HCl Granules", "API Granule"), ("Paracetamol", "API")]


def ensure_secret() -> None:
    env_file = ROOT / ".env"
    existing = os.environ.get("FLOWTOOL_SECRET_KEY") or \
        (dotenv_values(env_file).get("FLOWTOOL_SECRET_KEY") if env_file.exists() else None)
    if existing and len(existing) >= MIN_SECRET_LENGTH:
        return
    if existing:
        raise SystemExit("FLOWTOOL_SECRET_KEY is set but too short. Replace it, then re-run.")
    prefix = ""
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        prefix = "" if not content or content.endswith("\n") else "\n"
    with open(env_file, "a", encoding="utf-8") as fh:
        fh.write(f"{prefix}FLOWTOOL_SECRET_KEY={generate_secret()}\n")
    print("Created a signing key in .env (never commit this file).")


def main() -> None:
    ensure_secret()
    settings = load_settings()
    engine = build_engine(settings.database_url)
    init_db(engine)
    db = build_session_factory(engine)()
    created = []
    try:
        for email, name, role in SEED_USERS:
            already_has_superadmin = role == Role.superadmin and db.query(User).filter(
                User.role == Role.superadmin).count()
            if already_has_superadmin or db.query(User).filter(User.email == email).count():
                print(f"exists, skipped: {email}")
                continue
            password = secrets.token_urlsafe(12)
            user = User(email=email, full_name=name, role=role,
                        password_hash=hash_password(password))
            db.add(user)
            db.flush()
            db.add(PasswordChangeRequired(user_id=user.id))   # printed passwords are temporary
            created.append((email, role.value, password))
        for name, kind in MATERIALS:
            if not db.query(Material).filter(Material.name == name).count():
                db.add(Material(name=name, material_type=kind))
        db.commit()
    finally:
        db.close()
        engine.dispose()
    if created:
        print("\nPasswords are shown once. Save them now and change them after first login.\n")
        for email, role, password in created:
            print(f"{email:<32}{role:<12}{password}")


if __name__ == "__main__":
    main()
