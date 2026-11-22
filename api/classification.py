"""Run a classification and persist it with its audit record, atomically."""
from __future__ import annotations

import math

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from api.billing import enforce_plan
from api.db.models import EnginePath, Prediction, Role, Sample, User
from api.deps import audit
from src.features.flow_metrics import carrs_index, is_poor_flow
from src.models.engine import classify
from src.preprocessing.validation import FlowInputError

MEASUREMENT_FIELDS = ("bulk_density", "tapped_density", "angle_of_repose", "particle_size_um",
                      "moisture_percent", "flow_rate_g_s")


def get_accessible_sample(db: Session, sample_id: int, user: User) -> Sample:
    """Analysts see only their own samples; a 404 avoids revealing that others exist."""
    sample = db.get(Sample, sample_id)
    if sample is None or (user.role == Role.analyst and sample.operator_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such sample")
    return sample


def _same(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _check_sample_matches(sample: Sample, measurements: dict) -> None:
    if sample.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "This sample has been voided.")
    different = [f for f in MEASUREMENT_FIELDS
                 if not _same(measurements.get(f), getattr(sample, f))]
    if different:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Inputs differ from the recorded sample in: " + ", ".join(different)
            + ". Use POST /samples/{id}/classify to classify the recorded values.",
        )


def run_classification(db: Session, request: Request, user: User, measurements: dict,
                       sample_id: int | None = None) -> dict:
    if sample_id is not None:
        _check_sample_matches(get_accessible_sample(db, sample_id, user), measurements)
    enforce_plan(db, user, needs_ml=measurements.get("tapped_density") is None)
    try:
        result = classify(
            bulk_density=measurements["bulk_density"],
            tapped_density=measurements.get("tapped_density"),
            angle_of_repose=measurements.get("angle_of_repose"),
            particle_size=measurements.get("particle_size_um"),
            moisture=measurements.get("moisture_percent"),
            flow_rate=measurements.get("flow_rate_g_s"),
            bundles=request.app.state.bundles,
            ranges=request.app.state.training_ranges,
        )
    except FlowInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    row = Prediction(
        sample_id=sample_id, user_id=user.id, path=EnginePath(result.path),
        model_version=result.model_version, predicted_class=result.predicted_class,
        acceptable=result.acceptable, confidence=result.confidence,
        carr_index=result.carr_index, hausner=result.hausner,
        hausner_class=result.hausner_class, criteria_agree=result.criteria_agree,
        inputs={**{f: measurements.get(f) for f in MEASUREMENT_FIELDS}, "sample_id": sample_id},
        caveats=result.caveats, basis=result.basis,
    )
    db.add(row)
    db.flush()
    audit(db, user, "classify", "prediction", row.id,
          {"path": result.path, "class": result.predicted_class}, request)
    db.commit()
    return {**result.dict(), "prediction_id": row.id}


def derive_poor_flow(row: Prediction) -> bool | None:
    """Computed from stored inputs so that older rows get the same answer as new ones."""
    if row.path == EnginePath.rule:
        inputs = row.inputs or {}
        bulk, tapped = inputs.get("bulk_density"), inputs.get("tapped_density")
        if bulk and tapped:
            return is_poor_flow(carrs_index(bulk, tapped))
        return is_poor_flow(row.carr_index) if row.carr_index is not None else None
    if row.predicted_class.startswith("Poor flow"):
        return True
    if row.predicted_class.startswith("Acceptable (Carr's < 25)"):
        return False
    return None
