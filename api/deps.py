"""Shared FastAPI dependencies: database session, authentication, roles, audit."""
from __future__ import annotations

import hmac
from typing import Annotated, Iterator

from fastapi import Depends, HTTPException, Path, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from api.db.models import AuditLog, PasswordChangeRequired, Role, User
from api.security import decode_token, password_fingerprint
from src.config import Settings

MAX_INT = 2_147_483_647
bearer = HTTPBearer(auto_error=False)

ResourceId = Annotated[int, Path(ge=1, le=MAX_INT)]
Offset = Annotated[int, Query(ge=0, le=MAX_INT)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail,
                         headers={"WWW-Authenticate": "Bearer"})


PASSWORD_CHANGE_ALLOWED = {"/auth/me", "/auth/change-password"}


def require_password_change(db: Session, user: User) -> None:
    if db.get(PasswordChangeRequired, user.id) is None:
        db.add(PasswordChangeRequired(user_id=user.id))


def current_user(request: Request, db: DbSession, settings: AppSettings,
                 creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> User:
    if creds is None:
        raise _unauthorized("Not authenticated")
    payload = decode_token(settings.secret_key, creds.credentials)
    if not payload or not 1 <= payload["sub"] <= MAX_INT:
        raise _unauthorized("Invalid or expired token")
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise _unauthorized("User inactive or unknown")
    expected = password_fingerprint(settings.secret_key, user.password_hash)
    if not hmac.compare_digest(str(payload.get("pwv", "")), expected):
        raise _unauthorized("Invalid or expired token")
    if request.url.path not in PASSWORD_CHANGE_ALLOWED and \
            db.get(PasswordChangeRequired, user.id) is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Change your temporary password to continue.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require(*roles: Role):
    def guard(user: CurrentUser) -> User:
        if user.role not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"This action requires one of: {allowed}")
        return user
    return guard


def client_ip(request: Request | None) -> str | None:
    return request.client.host if request and request.client else None


def audit(db: Session, user: User | None, action: str, entity: str | None = None,
          entity_id: int | None = None, detail: dict | None = None,
          request: Request | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None,
                    actor_email=user.email if user else None,
                    action=action, entity=entity, entity_id=entity_id, detail=detail,
                    ip_address=client_ip(request)))
