"""Prediction history and independent review."""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import joinedload

from api.classification import derive_poor_flow
from api.db.models import STAFF, EnginePath, Prediction, Role, User, utcnow
from api.deps import CurrentUser, DbSession, Offset, ResourceId, audit, require
from api.schemas import ReviewIn

router = APIRouter(prefix="/predictions", tags=["predictions"])
Reviewer = Annotated[User, Depends(require(*STAFF))]


def _summary(row: Prediction) -> dict:
    return {
        "id": row.id, "sample_id": row.sample_id,
        "sample_voided": bool(row.sample and row.sample.is_voided),
        "path": row.path.value, "predicted_class": row.predicted_class,
        "poor_flow": derive_poor_flow(row), "acceptable": row.acceptable,
        "confidence": row.confidence, "carr_index": row.carr_index, "hausner": row.hausner,
        "model_version": row.model_version, "reviewed": row.reviewed_at is not None,
        "created_at": row.created_at,
    }


@router.get("")
def list_predictions(user: CurrentUser, db: DbSession,
                     limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Offset = 0,
                     path: Optional[EnginePath] = None, reviewed: Optional[bool] = None):
    query = db.query(Prediction).options(joinedload(Prediction.sample))
    if user.role == Role.analyst:
        query = query.filter(Prediction.user_id == user.id)
    if path is not None:
        query = query.filter(Prediction.path == path)
    if reviewed is not None:
        column = Prediction.reviewed_at
        query = query.filter(column.isnot(None) if reviewed else column.is_(None))
    rows = query.order_by(Prediction.created_at.desc(), Prediction.id.desc()) \
        .offset(offset).limit(limit).all()
    return [_summary(r) for r in rows]


@router.get("/{prediction_id}")
def get_prediction(prediction_id: ResourceId, user: CurrentUser, db: DbSession):
    row = db.get(Prediction, prediction_id)
    if row is None or (user.role == Role.analyst and row.user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such prediction")
    return {**_summary(row), "user_id": row.user_id, "inputs": row.inputs,
            "caveats": row.caveats, "basis": row.basis,
            "hausner_class": row.hausner_class, "criteria_agree": row.criteria_agree,
            "reviewed_by_id": row.reviewed_by_id, "reviewed_at": row.reviewed_at,
            "review_comment": row.review_comment}


@router.post("/{prediction_id}/review")
def review(prediction_id: ResourceId, request: Request, reviewer: Reviewer, db: DbSession,
           body: Annotated[Optional[ReviewIn], Body()] = None):
    row = db.get(Prediction, prediction_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such prediction")
    if row.user_id == reviewer.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "A result cannot be reviewed by the person who produced it.")
    if row.reviewed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This result has already been reviewed.")
    if row.sample is not None and row.sample.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This result's sample has been voided.")
    comment = body.comment if body else ""
    row.reviewed_by_id = reviewer.id
    row.reviewed_at = utcnow()
    row.review_comment = comment
    audit(db, reviewer, "review", "prediction", row.id, {"comment": comment}, request)
    db.commit()
    return {"ok": True, "reviewed_at": row.reviewed_at}
