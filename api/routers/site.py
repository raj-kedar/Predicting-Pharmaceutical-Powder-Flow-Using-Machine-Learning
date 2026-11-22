"""Public website content (team, guides, business details), edited by superadmins only."""
from __future__ import annotations

import copy
import datetime as dt
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from api.db.models import Role, SiteContent, StoredImage, User, utcnow
from api.deps import DbSession, audit, require
from api.media import image_response
from api.routers.profile import discard_image, store_image

router = APIRouter(prefix="/site", tags=["site"])
Superadmin = Annotated[User, Depends(require(Role.superadmin))]
ImageId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]
KEY = "site"

DEFAULT_CONTENT = {
    "team": [{"name": f"Team member {i}", "role": "Role", "photo_id": None} for i in range(1, 5)],
    "guides": [{"name": f"Project guide {i}", "role": "Faculty guide", "photo_id": None}
               for i in (1, 2)],
    "business": {"name": "[Registered business or owner name]", "email": "[support email]",
                 "phone": "[support phone]", "address": "[registered address]",
                 "last_updated": "[date]"},
}


def _text(value):
    """Collapse whitespace before length checks, so '   ' is rejected as empty."""
    return " ".join(value.split()) if isinstance(value, str) else value


class Person(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    role: str = Field("", max_length=120)
    photo_id: Optional[str] = Field(None, pattern=r"^[0-9a-f]{32}$")

    _clean = field_validator("name", "role", mode="before")(_text)


class Business(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=120)
    email: str = Field(max_length=254)
    phone: str = Field(max_length=40)
    address: str = Field(max_length=300)
    last_updated: str = Field(max_length=40)

    _clean = field_validator("*", mode="before")(_text)


class SiteContentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team: list[Person] = Field(max_length=8)
    guides: list[Person] = Field(max_length=4)
    business: Business


def _with_urls(value: dict) -> dict:
    out = copy.deepcopy(value)
    for group in ("team", "guides"):
        for person in out.get(group, []):
            pid = person.get("photo_id")
            person["photo_url"] = f"/site/photos/{pid}" if pid else None
    return out


def current_content(db) -> dict:
    row = db.get(SiteContent, KEY)
    return row.value if row else DEFAULT_CONTENT


@router.get("/content")
def get_content(db: DbSession):
    return _with_urls(current_content(db))


@router.put("/content")
def put_content(body: SiteContentIn, request: Request, user: Superadmin, db: DbSession):
    value = body.model_dump()
    ids = {p["photo_id"] for g in ("team", "guides") for p in value[g] if p["photo_id"]}
    if ids:
        found = set(db.scalars(select(StoredImage.id).where(StoredImage.id.in_(ids),
                                                            StoredImage.kind == "site")))
        if found != ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown photo reference.")
    row = db.get(SiteContent, KEY)
    if row is None:
        row = SiteContent(key=KEY, value=value)
        db.add(row)
    row.value = value
    row.updated_at = utcnow()
    row.updated_by_id = user.id
    audit(db, user, "update_site", "site", None, None, request)
    db.commit()

    # Remove site photos no longer used, once they are a day old (fresh uploads may be unsaved).
    cutoff = utcnow() - dt.timedelta(days=1)
    stale = db.scalars(select(StoredImage.id).where(StoredImage.kind == "site",
                                                    StoredImage.created_at < cutoff)).all()
    for image_id in stale:
        if image_id not in ids:
            discard_image(request, db, image_id)
    return _with_urls(value)


@router.post("/photos", status_code=201)
async def upload_site_photo(request: Request, user: Superadmin, db: DbSession):
    data = await request.body()
    content_type = request.headers.get("content-type", "")

    def work():
        image = store_image(request, db, user, data, content_type, "site")
        db.commit()
        return {"id": image.id, "url": f"/site/photos/{image.id}"}

    return await run_in_threadpool(work)


@router.get("/photos/{image_id}")
def site_photo(image_id: ImageId, request: Request, db: DbSession):
    image = db.get(StoredImage, image_id)
    if image is None or image.kind != "site":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    data = request.app.state.storage.get(image.storage_key)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    # Public team photos: same-origin only, so other websites cannot embed them.
    return image_response(data, "public, max-age=86400")
