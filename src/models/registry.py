"""
Safe model loading.

pickle can execute arbitrary code, so a bundle is loaded only if its SHA-256
matches models/manifest.json, and then only through an allowlist of classes.
Bundles trained before the restructure reference `app.forest`; that path is
mapped to `src.models.forest`, so the validated files are used byte-for-byte.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.models import forest

log = logging.getLogger(__name__)

TIERS = ("full", "mid", "basic")
MANIFEST_NAME = "manifest.json"
FEATURES = ["Bulk_Density_g_mL", "Angle_of_Repose_deg", "Mean_Particle_Size_um",
            "Moisture_Content_percent", "Flow_Rate_g_s"]
_REQUIRED_KEYS = {"model", "features", "classes", "version", "tier", "lomo_accuracy",
                  "lomo_balanced_acc", "majority_baseline", "n_materials"}

_NUMPY_GLOBALS = {
    ("numpy", "ndarray"), ("numpy", "dtype"),
    ("numpy._core.multiarray", "_reconstruct"), ("numpy._core.multiarray", "scalar"),
    ("numpy.core.multiarray", "_reconstruct"), ("numpy.core.multiarray", "scalar"),
    ("numpy.random._pickle", "__generator_ctor"),
    ("numpy.random._pickle", "__bit_generator_ctor"),
    ("numpy.random._pcg64", "PCG64"),
    ("numpy.random.bit_generator", "__pyx_unpickle_SeedSequence"),
    ("numpy.random.bit_generator", "SeedSequence"),
}
_FOREST_MODULES = {"app.forest", "src.models.forest"}
_FOREST_CLASSES = {"Forest", "Tree"}


class ModelLoadError(RuntimeError):
    """A model file failed verification and was not loaded."""


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if module in _FOREST_MODULES and name in _FOREST_CLASSES:
            return getattr(forest, name)
        if (module, name) in _NUMPY_GLOBALS:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Blocked global in model file: {module}.{name}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tier_path(model_dir: Path, tier: str, version: str) -> Path:
    return model_dir / f"poor_flow_{tier}_v{version}.pkl"


def write_manifest(model_dir: Path, version: str, training_frame: pd.DataFrame) -> Path:
    """Record model checksums and the input range each model was trained on."""
    files = {}
    for tier in TIERS:
        path = tier_path(model_dir, tier, version)
        files[path.name] = sha256(path)
    ranges = {f: [float(training_frame[f].min()), float(training_frame[f].max())]
              for f in FEATURES}
    target = model_dir / MANIFEST_NAME
    target.write_text(json.dumps({"version": version, "files": files, "training_ranges": ranges},
                                 indent=2), encoding="utf-8")
    return target


def _check_bundle(bundle: Any, tier: str, version: str) -> None:
    if not isinstance(bundle, dict) or not _REQUIRED_KEYS <= bundle.keys():
        raise ModelLoadError(f"{tier}: bundle is missing required fields")
    if bundle["tier"] != tier or bundle["version"] != version:
        raise ModelLoadError(f"{tier}: bundle identity does not match its filename")
    if len(bundle["classes"]) != 2 or not set(bundle["features"]) <= set(FEATURES):
        raise ModelLoadError(f"{tier}: unexpected classes or features")
    probe = np.ones((1, len(bundle["features"])))
    proba = bundle["model"].predict_proba(probe)[0]
    if len(proba) != 2 or not all(math.isfinite(p) for p in proba) \
            or not math.isclose(float(sum(proba)), 1.0, abs_tol=1e-6):
        raise ModelLoadError(f"{tier}: model produced invalid probabilities")


def load_bundles(model_dir: Path, version: str) -> tuple[dict[str, dict], dict[str, list[float]]]:
    """Return (verified bundles, training ranges). A bad tier is skipped, never trusted."""
    manifest_path = model_dir / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = manifest["files"]
        ranges = manifest["training_ranges"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.error("Model manifest unavailable (%s). ML tiers are disabled.", exc)
        return {}, {}

    bundles: dict[str, dict] = {}
    for tier in TIERS:
        path = tier_path(model_dir, tier, version)
        try:
            if path.name not in expected or sha256(path) != expected[path.name]:
                raise ModelLoadError(f"{tier}: checksum mismatch")
            with open(path, "rb") as fh:
                bundle = _RestrictedUnpickler(fh).load()
            _check_bundle(bundle, tier, version)
        except Exception as exc:  # any corrupt file must disable the tier, not the API
            log.error("Tier '%s' not loaded: %s", tier, exc)
            continue
        bundles[tier] = bundle
        log.info("Loaded tier '%s' (LOMO accuracy %.3f)", tier, bundle["lomo_accuracy"])
    return bundles, ranges
