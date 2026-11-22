"""Health, readiness and model transparency."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(tags=["system"])


@router.get("/health")
def health(request: Request):
    """Liveness: the process is up."""
    bundles = request.app.state.bundles
    return {"status": "ok", "model_loaded": bool(bundles), "tiers": list(bundles)}


@router.get("/ready")
def ready(request: Request):
    """Readiness: the database answers. The exact path works even with no models."""
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "unavailable", "database": False}, status_code=503)
    return {"status": "ready", "database": True, "tiers": list(request.app.state.bundles)}


@router.get("/model-card")
def model_card(request: Request):
    bundles = request.app.state.bundles
    if not bundles:
        raise HTTPException(503, "No model loaded. Run: python -m scripts.train")
    return {
        "exact_path": {
            "when": "bulk density AND tapped density supplied",
            "method": "USP <1174> compressibility index band",
            "accuracy": "exact by definition - not a prediction",
        },
        "ml_tiers": {tier: {k: v for k, v in bundle.items() if k != "model"}
                     for tier, bundle in bundles.items()},
        "training_ranges": request.app.state.training_ranges,
    }
