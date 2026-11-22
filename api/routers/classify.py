"""The main endpoint: exact classification when possible, screening estimate otherwise."""
from __future__ import annotations

from fastapi import APIRouter, Request

from api.classification import run_classification
from api.deps import CurrentUser, DbSession
from api.schemas import ClassifyIn

router = APIRouter(tags=["classify"])


@router.post("/classify")
def do_classify(body: ClassifyIn, request: Request, user: CurrentUser, db: DbSession):
    """The `path` field in the response says whether the answer is exact or an estimate."""
    measurements = body.model_dump(exclude={"sample_id"})
    return run_classification(db, request, user, measurements, body.sample_id)
