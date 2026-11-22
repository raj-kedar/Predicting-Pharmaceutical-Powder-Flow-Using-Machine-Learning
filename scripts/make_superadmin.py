"""
Promote an existing account to superadmin, optionally changing its email. Run on the
server (there is no web route that can create the first superadmin).

Usage:
  python -m scripts.make_superadmin admin@example.com
  python -m scripts.make_superadmin admin@flowtool.local --new-email owner@example.com
  python -m scripts.make_superadmin owner@example.com --temporary-password 'CHOOSE-ONE'
"""
from __future__ import annotations

import argparse

from api.db.models import AuditLog, Role, User
from api.db.session import build_engine, build_session_factory, init_db
from api.deps import require_password_change
from api.schemas import _check_email
from api.security import hash_password
from src.config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", help="current email of the account")
    parser.add_argument("--new-email", help="also change the account's sign-in email")
    parser.add_argument("--temporary-password",
                        help="set a first-time password that must be changed at first sign-in")
    args = parser.parse_args()
    temporary = args.temporary_password
    if temporary is not None and not 8 <= len(temporary) <= 256:
        raise SystemExit("The temporary password must be 8 to 256 characters.")
    try:
        current = _check_email(args.email)
        new_email = _check_email(args.new_email) if args.new_email else None
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    settings = load_settings()
    engine = build_engine(settings.database_url)
    init_db(engine)
    db = build_session_factory(engine)()
    try:
        user = db.query(User).filter(User.email == current).one_or_none()
        if user is None:
            raise SystemExit(f"No account with email {current}")
        if not user.is_active:
            raise SystemExit("That account is deactivated.")
        if new_email and new_email != user.email and \
                db.query(User).filter(User.email == new_email).count():
            raise SystemExit(f"{new_email} is already used by another account.")

        detail = {"from_role": user.role.value, "by": "server console"}
        if new_email and new_email != user.email:
            detail.update(from_email=user.email, to_email=new_email)
            user.email = new_email
        user.role = Role.superadmin
        if temporary is not None:
            user.password_hash = hash_password(temporary)   # also signs out old sessions
            require_password_change(db, user)
            detail["temporary_password"] = True             # recorded, never the value
        db.add(AuditLog(action="promote_superadmin", entity="user", entity_id=user.id,
                        detail=detail))
        db.commit()
        password_note = ("Sign in with the temporary password; it must be changed immediately."
                         if temporary is not None else "The password is unchanged.")
        print(f"{user.email} is now a superadmin (was {detail['from_role']}). {password_note}")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
