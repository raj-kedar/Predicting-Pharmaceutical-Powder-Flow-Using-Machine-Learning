"""Read-only access to the audit trail."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from api.db.models import ADMINS, AuditLog, User
from api.deps import DbSession, Offset, require

router = APIRouter(tags=["audit"])


@router.get("/audit")
def read_audit(admin: Annotated[User, Depends(require(*ADMINS))], db: DbSession,
               limit: Annotated[int, Query(ge=1, le=500)] = 100, offset: Offset = 0,
               action: Annotated[Optional[str], Query(max_length=64)] = None):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    rows = query.order_by(AuditLog.at.desc(), AuditLog.id.desc()).offset(offset).limit(limit).all()
    return [{"id": r.id, "at": r.at, "actor": r.actor_email, "action": r.action,
             "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail,
             "ip_address": r.ip_address} for r in rows]
