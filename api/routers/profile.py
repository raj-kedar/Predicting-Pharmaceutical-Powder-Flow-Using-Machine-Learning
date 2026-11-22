"""
Profile photos with a privacy lock (similar to a locked social-media profile).

A locked photo is visible only to its owner and to admins. An unlocked photo is visible
to signed-in users. Photos are never public, and anyone not allowed to see one gets 404,
so the API does not even reveal that a photo exists.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from api.db.models import ADMINS, AuditLog, Role, StoredImage, User, UserProfile, utcnow
from api.deps import CurrentUser, DbSession, ResourceId, audit, require
from api.media import image_response, new_image_id, sanitize_image, storage_key

router = APIRouter(tags=["profile"])
log = logging.getLogger("flowlytix.media")
Admin = Annotated[User, Depends(require(*ADMINS))]
UPLOADS_PER_HOUR = 20


class LockIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_locked: StrictBool   # "no", 0 or "false" must not silently unlock a photo


def _profile(db, user_id: int, create: bool = False) -> UserProfile | None:
    row = db.get(UserProfile, user_id)
    if row is None and create:
        row = UserProfile(user_id=user_id, photo_locked=True)
        db.add(row)
    return row


def _out(row: UserProfile | None, user_id: int) -> dict:
    has = bool(row and row.photo_id)
    return {"has_photo": has, "photo_locked": row.photo_locked if row else True,
            "photo_url": f"/profile/{user_id}/photo?v={row.photo_id[:8]}" if has else None}


def check_upload_rate(db, user: User) -> None:
    recent = db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.user_id == user.id, AuditLog.action == "upload_image",
        AuditLog.at > utcnow() - dt.timedelta(hours=1))) or 0
    if recent >= UPLOADS_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many uploads. Try again later.")


def store_image(request: Request, db, user: User, data: bytes, content_type: str,
                kind: str) -> StoredImage:
    """Validate, re-encode and store. Raises 422 for unsafe files, 503 if storage fails."""
    check_upload_rate(db, user)
    clean = sanitize_image(data, content_type, kind)
    image_id = new_image_id()
    key = storage_key(kind, image_id)
    try:
        request.app.state.storage.put(key, clean.data)
    except Exception as exc:
        log.error("Image storage failed: %s", exc)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Image storage is unavailable. Try again later.") from exc
    row = StoredImage(id=image_id, kind=kind, storage_key=key, width=clean.width,
                      height=clean.height, size_bytes=len(clean.data), sha256=clean.sha256,
                      uploaded_by_id=user.id)
    db.add(row)
    audit(db, user, "upload_image", "image", None, {"id": image_id, "kind": kind}, request)
    return row


def discard_image(request: Request, db, image_id: str | None) -> None:
    if not image_id:
        return
    row = db.get(StoredImage, image_id)
    if row is None:
        return
    key = row.storage_key
    db.delete(row)
    db.commit()
    try:
        request.app.state.storage.delete(key)
    except Exception as exc:   # the database no longer points at it; log and move on
        log.warning("Could not delete stored image %s: %s", key, exc)


@router.get("/profile/me")
def my_profile(user: CurrentUser, db: DbSession):
    return _out(_profile(db, user.id), user.id)


@router.put("/profile/me/photo")
async def upload_photo(request: Request, user: CurrentUser, db: DbSession):
    data = await request.body()
    content_type = request.headers.get("content-type", "")

    def work():
        profile = _profile(db, user.id, create=True)
        image = store_image(request, db, user, data, content_type, "profile")
        old = profile.photo_id
        db.flush()
        profile.photo_id = image.id
        profile.updated_at = utcnow()
        db.commit()
        discard_image(request, db, old)
        return _out(profile, user.id)

    return await run_in_threadpool(work)


@router.delete("/profile/me/photo")
def delete_photo(request: Request, user: CurrentUser, db: DbSession):
    profile = _profile(db, user.id)
    if profile is None or not profile.photo_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile photo")
    old, profile.photo_id = profile.photo_id, None
    audit(db, user, "delete_image", "image", None, {"id": old}, request)
    db.commit()
    discard_image(request, db, old)
    return _out(profile, user.id)


@router.patch("/profile/me")
def set_lock(body: LockIn, request: Request, user: CurrentUser, db: DbSession):
    profile = _profile(db, user.id, create=True)
    profile.photo_locked = body.photo_locked
    profile.updated_at = utcnow()
    audit(db, user, "photo_lock", "user", user.id, {"locked": body.photo_locked}, request)
    db.commit()
    return _out(profile, user.id)


@router.get("/profile/{user_id}/photo")
def view_photo(user_id: ResourceId, request: Request, viewer: CurrentUser, db: DbSession):
    profile = _profile(db, user_id)
    allowed = profile is not None and profile.photo_id and (
        viewer.id == user_id or viewer.role in ADMINS or not profile.photo_locked)
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    image = db.get(StoredImage, profile.photo_id)
    data = request.app.state.storage.get(image.storage_key) if image else None
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    return image_response(data, "private, no-store")


@router.delete("/admin/users/{user_id}/photo")
def moderate_photo(user_id: ResourceId, request: Request, admin: Admin, db: DbSession):
    """Remove an inappropriate profile photo."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    if target.role == Role.superadmin and admin.role != Role.superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a superadmin can manage superadmin accounts.")
    profile = _profile(db, user_id)
    if profile is None or not profile.photo_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile photo")
    old, profile.photo_id = profile.photo_id, None
    audit(db, admin, "remove_photo", "user", user_id, {"id": old}, request)
    db.commit()
    discard_image(request, db, old)
    return {"ok": True}
