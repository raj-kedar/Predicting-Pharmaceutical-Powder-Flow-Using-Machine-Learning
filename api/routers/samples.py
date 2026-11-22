"""Measurement records. Samples are voided with a reason, never edited or deleted."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from api.classification import MEASUREMENT_FIELDS, get_accessible_sample, run_classification
from api.db.models import Material, Role, Sample
from api.deps import CurrentUser, DbSession, Offset, ResourceId, audit
from api.schemas import MaterialOut, SampleIn, SampleOut, VoidIn

router = APIRouter(tags=["samples"])
_DUPLICATE = "This material, batch and replicate number is already recorded."


def _out(sample: Sample) -> SampleOut:
    return SampleOut(
        id=sample.id, material_id=sample.material_id, material_name=sample.material.name,
        operator_id=sample.operator_id, batch_no=sample.batch_no,
        replicate_no=sample.replicate_no, measured_at=sample.measured_at,
        sample_weight_g=sample.sample_weight_g, bulk_density=sample.bulk_density,
        tapped_density=sample.tapped_density, angle_of_repose=sample.angle_of_repose,
        particle_size_um=sample.particle_size_um, moisture_percent=sample.moisture_percent,
        flow_rate_g_s=sample.flow_rate_g_s, method_ref=sample.method_ref, notes=sample.notes,
        is_voided=sample.is_voided, void_reason=sample.void_reason,
    )


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(user: CurrentUser, db: DbSession,
                   limit: Annotated[int, Query(ge=1, le=500)] = 200, offset: Offset = 0):
    return db.query(Material).order_by(Material.name, Material.id) \
        .offset(offset).limit(limit).all()


@router.post("/samples", status_code=201)
def create_sample(body: SampleIn, request: Request, user: CurrentUser, db: DbSession):
    material = db.query(Material).filter(
        func.lower(Material.name) == body.material_name.lower()).first()
    try:
        if material is None:
            material = Material(name=body.material_name, material_type=body.material_type,
                                created_by_id=user.id)
            db.add(material)
            db.flush()
        sample = Sample(
            material_id=material.id, operator_id=user.id, batch_no=body.batch_no,
            replicate_no=body.replicate_no, sample_weight_g=body.sample_weight_g,
            method_ref=body.method_ref, notes=body.notes,
            **{f: getattr(body, f) for f in MEASUREMENT_FIELDS},
        )
        db.add(sample)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _DUPLICATE) from exc
    audit(db, user, "create", "sample", sample.id,
          {"material": material.name, "batch": body.batch_no}, request)
    db.commit()
    return {"sample_id": sample.id, "material_id": material.id}


@router.get("/samples", response_model=list[SampleOut])
def list_samples(user: CurrentUser, db: DbSession,
                 limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Offset = 0,
                 include_voided: bool = False):
    query = db.query(Sample).options(joinedload(Sample.material))
    if user.role == Role.analyst:
        query = query.filter(Sample.operator_id == user.id)
    if not include_voided:
        query = query.filter(Sample.is_voided.is_(False))
    rows = query.order_by(Sample.created_at.desc(), Sample.id.desc()) \
        .offset(offset).limit(limit).all()
    return [_out(r) for r in rows]


@router.get("/samples/{sample_id}", response_model=SampleOut)
def get_sample(sample_id: ResourceId, user: CurrentUser, db: DbSession):
    return _out(get_accessible_sample(db, sample_id, user))


@router.post("/samples/{sample_id}/classify")
def classify_sample(sample_id: ResourceId, request: Request, user: CurrentUser, db: DbSession):
    """Classify exactly what was recorded, with no chance of retyping a value wrongly."""
    sample = get_accessible_sample(db, sample_id, user)
    measurements = {f: getattr(sample, f) for f in MEASUREMENT_FIELDS}
    return run_classification(db, request, user, measurements, sample.id)


@router.post("/samples/{sample_id}/void", response_model=SampleOut)
def void_sample(sample_id: ResourceId, body: VoidIn, request: Request, user: CurrentUser,
                db: DbSession):
    sample = get_accessible_sample(db, sample_id, user)
    if sample.is_voided:
        raise HTTPException(status.HTTP_409_CONFLICT, "This sample is already voided.")
    sample.is_voided = True
    sample.void_reason = body.reason
    audit(db, user, "void", "sample", sample.id, {"reason": body.reason}, request)
    db.commit()
    return _out(sample)
