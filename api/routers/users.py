"""
Admin user management. Users are deactivated, never deleted.

Admins manage analysts, reviewers and admins. Only a superadmin can create, change or
promote to superadmin. The last active admin-level account and the last active
superadmin can never be removed.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError

from api.db.models import ADMINS, Role, User
from api.deps import DbSession, Offset, ResourceId, audit, require, require_password_change
from api.schemas import UserIn, UserOut, UserUpdate
from api.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])
Admin = Annotated[User, Depends(require(*ADMINS))]
_SUPER_ONLY = "Only a superadmin can manage superadmin accounts."


def _others(db, roles, user_id: int) -> int:
    return db.query(User).filter(User.role.in_(roles), User.is_active.is_(True),
                                 User.id != user_id).count()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserIn, request: Request, admin: Admin, db: DbSession):
    if body.role == Role.superadmin and admin.role != Role.superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, _SUPER_ONLY)
    if db.query(User).filter(User.email == body.email).count():
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered.")
    user = User(email=body.email, full_name=body.full_name,
                password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That email is already registered.") from exc
    require_password_change(db, user)   # an admin chose this password, so it is temporary
    audit(db, admin, "create", "user", user.id, {"email": user.email, "role": user.role.value},
          request)
    db.commit()
    return user


@router.get("", response_model=list[UserOut])
def list_users(admin: Admin, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 100,
               offset: Offset = 0):
    return db.query(User).order_by(User.id).offset(offset).limit(limit).all()


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: ResourceId, body: UserUpdate, request: Request, admin: Admin,
                db: DbSession):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    fields = body.model_fields_set
    if admin.role != Role.superadmin and (
            user.role == Role.superadmin or ("role" in fields and body.role == Role.superadmin)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, _SUPER_ONLY)

    deactivating = "is_active" in fields and body.is_active is False
    new_role = body.role if "role" in fields else user.role
    if user.is_active and user.role in ADMINS and (deactivating or new_role not in ADMINS):
        if not _others(db, ADMINS, user.id):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "This is the last active admin and cannot be removed.")
    if user.is_active and user.role == Role.superadmin and (
            deactivating or new_role != Role.superadmin):
        if not _others(db, (Role.superadmin,), user.id):
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "This is the last active superadmin and cannot be removed.")

    changed = sorted(fields)
    for name in changed:
        if name == "password":
            user.password_hash = hash_password(body.password)
            require_password_change(db, user)
        else:
            setattr(user, name, getattr(body, name))
    audit(db, admin, "update", "user", user.id, {"fields": changed}, request)
    db.commit()
    return user
