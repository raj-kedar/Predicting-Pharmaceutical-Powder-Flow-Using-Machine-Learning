"""Login with lockout, current user, and password change."""
from __future__ import annotations

import datetime as dt
import math

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import AuditLog, LoginThrottle, PasswordChangeRequired, Role, User, utcnow
from api.deps import AppSettings, CurrentUser, DbSession, audit, client_ip
from api.schemas import ChangePasswordIn, LoginIn, RegisterIn, TokenOut, UserOut
from api.security import burn_password_check, create_token, hash_password, verify_password
from src.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])
_BAD_LOGIN = "Incorrect email or password"


def _must_change(db: Session, user: User) -> bool:
    return db.get(PasswordChangeRequired, user.id) is not None


def _token(user: User, settings: Settings, must_change: bool = False) -> TokenOut:
    token = create_token(settings.secret_key, user.id, user.email, user.role.value,
                         user.password_hash, settings.token_ttl_seconds)
    return TokenOut(access_token=token, role=user.role.value, full_name=user.full_name,
                    must_change_password=must_change)


def _record_failure(db: Session, key: str, user: User | None, email: str, request: Request,
                    settings: Settings) -> None:
    now = utcnow()
    db.execute(delete(LoginThrottle).where(
        LoginThrottle.updated_at < now - dt.timedelta(days=1)))
    row = db.get(LoginThrottle, key)
    if row is None:
        row = LoginThrottle(key=key, failures=0)
        db.add(row)
    row.failures += 1
    row.updated_at = now
    if row.failures >= settings.max_login_failures:
        row.failures = 0
        row.locked_until = now + dt.timedelta(minutes=settings.lockout_minutes)
    audit(db, user, "login_failed", "user", user.id if user else None,
          None if user else {"email": email}, request)
    try:
        db.commit()
    except IntegrityError:  # a concurrent first failure created the row; the 401 still stands
        db.rollback()


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: DbSession, settings: AppSettings):
    key = f"{body.email}|{client_ip(request) or 'unknown'}"
    throttle = db.get(LoginThrottle, key)
    now = utcnow()
    if throttle and throttle.locked_until and throttle.locked_until > now:
        retry = math.ceil((throttle.locked_until - now).total_seconds())
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many failed attempts. Try again later.",
                            headers={"Retry-After": str(retry)})

    user = db.query(User).filter(User.email == body.email).one_or_none()
    if user is None:
        burn_password_check(body.password)
        valid = False
    else:
        valid = verify_password(body.password, user.password_hash) and user.is_active

    if not valid:
        _record_failure(db, key, user, body.email, request, settings)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_LOGIN,
                            headers={"WWW-Authenticate": "Bearer"})

    if throttle:
        db.delete(throttle)
    user.last_login_at = now
    audit(db, user, "login", "user", user.id, request=request)
    db.commit()
    return _token(user, settings, _must_change(db, user))


REGISTRATIONS_PER_HOUR = 10


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: DbSession, settings: AppSettings):
    """Self sign-up. New accounts are analysts on the Free plan."""
    if not settings.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-up is closed on this server.")
    ip = client_ip(request)
    recent = db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.action == "register", AuditLog.ip_address == ip,
        AuditLog.at > utcnow() - dt.timedelta(hours=1))) or 0
    if recent >= REGISTRATIONS_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Too many sign-ups from this network. Try again later.")
    if db.query(User).filter(User.email == body.email).count():
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with this email already exists. Sign in instead.")
    user = User(email=body.email, full_name=body.full_name, role=Role.analyst,
                password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with this email already exists.") from exc
    audit(db, user, "register", "user", user.id, request=request)
    db.commit()
    return _token(user, settings)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser, db: DbSession):
    return UserOut.model_validate(user).model_copy(
        update={"must_change_password": _must_change(db, user)})


@router.post("/change-password", response_model=TokenOut)
def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, db: DbSession,
                    settings: AppSettings):
    """Revokes every existing token for this user and returns a fresh one."""
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "New password must differ from the current one.")
    user.password_hash = hash_password(body.new_password)
    flag = db.get(PasswordChangeRequired, user.id)
    if flag is not None:
        db.delete(flag)
    audit(db, user, "change_password", "user", user.id, request=request)
    db.commit()
    return _token(user, settings)
