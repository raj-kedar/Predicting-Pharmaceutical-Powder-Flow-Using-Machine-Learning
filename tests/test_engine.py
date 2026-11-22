import json
import pickle

import pytest

from src.features.flow_metrics import CARR_EDGES, USP_CLASSES, band, carrs_index, is_poor_flow
from src.models.engine import classify, classify_rule
from src.models.registry import MANIFEST_NAME, load_bundles, tier_path
from src.preprocessing.validation import FlowInputError

VERSION = "1.1.0"


@pytest.mark.parametrize("value,expected", [
    (10.0, "Excellent"), (10.01, "Good"), (15.0, "Good"), (20.0, "Fair"), (25.0, "Passable"),
    (31.0, "Poor"), (37.0, "Very poor"), (37.01, "Very, very poor"),
])
def test_usp_band_edges(value, expected):
    assert USP_CLASSES[band(value, CARR_EDGES)] == expected


def test_float_noise_does_not_change_the_class():
    assert (0.1 - 0.09) / 0.1 * 100 > 10  # the raw float really is above the edge
    assert classify_rule(0.09, 0.1).predicted_class == "Excellent"
    assert (0.6 - 0.45) / 0.6 * 100 < 25  # and this one really is below the threshold
    assert classify_rule(0.45, 0.6).poor_flow is True


def test_exactly_25_is_poor_flow_and_not_acceptable():
    result = classify_rule(0.75, 1.0)
    assert result.carr_index == 25.0 and result.poor_flow and not result.acceptable


def test_middle_zone_is_neither_acceptable_nor_poor():
    result = classify_rule(0.78, 1.0)
    assert not result.acceptable and not result.poor_flow


def test_unrounded_value_decides_the_flag():
    assert not is_poor_flow(carrs_index(0.75004, 1.0))


def test_equal_densities_are_valid():
    result = classify_rule(0.5, 0.5)
    assert result.carr_index == 0 and result.hausner == 1


@pytest.mark.parametrize("bulk,tapped", [(0.6, 0.5), (0, 1), (-1, 1), (6, 7),
                                         (float("nan"), 1), (float("inf"), 1), (0.5, float("nan"))])
def test_impossible_densities_rejected(bulk, tapped):
    with pytest.raises(FlowInputError):
        classify_rule(bulk, tapped)


def test_tapped_density_bypasses_models():
    assert classify(0.5, 0.6, angle_of_repose=30, bundles=None).path == "rule"


def test_needs_tapped_or_angle():
    with pytest.raises(FlowInputError):
        classify(0.5)


def test_ml_without_models_is_a_clear_error():
    with pytest.raises(FlowInputError, match="No model"):
        classify(0.5, angle_of_repose=30, bundles={})


def test_tier_selection_and_ignored_inputs(model_dir):
    bundles, ranges = load_bundles(model_dir, VERSION)
    full = classify(0.5, None, 30, 100, 3, 4, bundles, ranges)
    mid = classify(0.5, None, 30, 100, 3, None, bundles, ranges)
    basic = classify(0.5, None, 30, None, None, 4, bundles, ranges)
    assert full.model_version.endswith("/full")
    assert mid.model_version.endswith("/mid")
    assert basic.model_version.endswith("/basic")
    assert any("not used by this tier: flow rate" in c for c in basic.caveats)


def test_out_of_range_input_is_flagged(model_dir):
    bundles, ranges = load_bundles(model_dir, VERSION)
    result = classify(0.5, None, 80, None, None, None, bundles, ranges)
    assert any("OUTSIDE TRAINING RANGE" in c for c in result.caveats)


def test_load_good_models(model_dir):
    bundles, ranges = load_bundles(model_dir, VERSION)
    assert set(bundles) == {"full", "mid", "basic"} and ranges


@pytest.fixture
def model_copy(model_dir, tmp_path):
    for path in model_dir.iterdir():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    return tmp_path


def test_tampered_model_is_not_loaded(model_copy):
    path = tier_path(model_copy, "full", VERSION)
    path.write_bytes(path.read_bytes() + b"x")
    assert set(load_bundles(model_copy, VERSION)[0]) == {"mid", "basic"}


def test_missing_manifest_disables_ml(model_copy):
    (model_copy / MANIFEST_NAME).unlink()
    assert load_bundles(model_copy, VERSION)[0] == {}


class _Exploit:
    def __reduce__(self):
        import os
        return os.system, ("echo pwned",)


def test_malicious_pickle_is_blocked_even_with_valid_checksum(model_copy):
    import hashlib
    path = tier_path(model_copy, "full", VERSION)
    path.write_bytes(pickle.dumps(_Exploit()))
    manifest_path = model_copy / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text())
    manifest["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    assert "full" not in load_bundles(model_copy, VERSION)[0]
