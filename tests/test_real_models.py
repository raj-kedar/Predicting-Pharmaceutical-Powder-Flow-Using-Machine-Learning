"""Checks the shipped v1.1.0 models. Skipped where model files are not present (e.g. CI)."""
import pytest

from src.config import ROOT
from src.models.engine import classify
from src.models.registry import MANIFEST_NAME, load_bundles

MODEL_DIR = ROOT / "models"
pytestmark = pytest.mark.skipif(not (MODEL_DIR / MANIFEST_NAME).exists(),
                                reason="trained models not present")
EXPECTED = {"full": 0.920, "mid": 0.847, "basic": 0.828}


def test_shipped_models_load_with_published_accuracy():
    bundles, _ = load_bundles(MODEL_DIR, "1.1.0")
    assert set(bundles) == set(EXPECTED)
    for tier, accuracy in EXPECTED.items():
        assert bundles[tier]["lomo_accuracy"] == pytest.approx(accuracy, abs=0.001)
        assert bundles[tier]["n_materials"] == 70


def test_shipped_model_predicts():
    bundles, ranges = load_bundles(MODEL_DIR, "1.1.0")
    result = classify(0.5, None, 35, 100, 3, 4, bundles, ranges)
    assert result.path == "ml" and result.model_version == "1.1.0/full"
    assert 0.5 <= result.confidence <= 1
