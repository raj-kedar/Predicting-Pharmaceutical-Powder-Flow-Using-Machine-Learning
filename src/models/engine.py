"""
Flowability engine.

RULE: Carr's index and Hausner ratio from measured densities, banded per
      USP <1174>. Exact by definition.
ML:   screening estimate used only when tapped density was not measured.
      Validated leave-one-material-out.

Every result carries `path`, so an estimate cannot be mistaken for a measurement.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from src.features.flow_metrics import (CARR_EDGES, HAUSNER_EDGES, USP_CLASSES, band, carrs_index,
                                       hausner_ratio, is_acceptable, is_poor_flow)
from src.models.registry import TIERS
from src.preprocessing.validation import FlowInputError, validate_densities

_LABELS = {
    "Bulk_Density_g_mL": "bulk density",
    "Angle_of_Repose_deg": "angle of repose",
    "Mean_Particle_Size_um": "particle size",
    "Moisture_Content_percent": "moisture",
    "Flow_Rate_g_s": "flow rate",
}


@dataclass
class FlowResult:
    path: str
    predicted_class: str
    poor_flow: bool
    acceptable: bool | None = None
    carr_index: float | None = None
    hausner: float | None = None
    hausner_class: str | None = None
    criteria_agree: bool | None = None
    confidence: float | None = None
    model_version: str | None = None
    basis: str = ""
    caveats: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


def classify_rule(bulk_density: float, tapped_density: float) -> FlowResult:
    validate_densities(bulk_density, tapped_density)
    ci = carrs_index(bulk_density, tapped_density)
    hr = hausner_ratio(bulk_density, tapped_density)
    ci_class = USP_CLASSES[band(ci, CARR_EDGES)]
    hr_class = USP_CLASSES[band(hr, HAUSNER_EDGES)]
    caveats = []
    if ci_class != hr_class:
        caveats.append(
            f"The two USP <1174> criteria disagree: Carr's index gives '{ci_class}' while "
            f"Hausner ratio gives '{hr_class}'. Carr's index is reported as primary. "
            "Disagreement is expected near a band edge."
        )
    return FlowResult(
        path="rule", predicted_class=ci_class, poor_flow=is_poor_flow(ci),
        acceptable=is_acceptable(ci), carr_index=round(ci, 2), hausner=round(hr, 3),
        hausner_class=hr_class, criteria_agree=ci_class == hr_class, confidence=1.0,
        basis="USP <1174> compressibility index band. Deterministic, not a prediction.",
        caveats=caveats,
    )


def select_tier(supplied: dict, bundles: dict) -> tuple[str | None, dict | None]:
    for tier in TIERS:
        bundle = bundles.get(tier)
        if bundle and all(supplied.get(f) is not None for f in bundle["features"]):
            return tier, bundle
    return None, None


def _ml_caveats(tier: str, bundle: dict, bundles: dict, supplied: dict, ranges: dict) -> list[str]:
    features = bundle["features"]
    caveats = [
        "ESTIMATE, not a measurement. Tapped density was not supplied, so the exact "
        "pharmacopoeial class could not be computed.",
        f"Tier '{tier}' ({len(features)} input(s)), validated leave-one-material-out on "
        f"{bundle['n_materials']} materials: accuracy {bundle['lomo_accuracy']:.1%}, balanced "
        f"accuracy {bundle['lomo_balanced_acc']:.2f}, against a "
        f"{bundle['majority_baseline']:.1%} majority baseline. Behaviour on a material "
        "unlike the training set is unknown.",
    ]
    ignored = [_LABELS[f] for f, v in supplied.items() if v is not None and f not in features]
    if ignored:
        caveats.append(
            f"Supplied but not used by this tier: {', '.join(ignored)}. The richer tier also "
            "needs the remaining measurements."
        )
    full = bundles.get("full")
    if tier != "full" and full:
        missing = [_LABELS[f] for f in full["features"] if supplied.get(f) is None]
        caveats.append(
            f"Adding {', '.join(missing)} enables the full tier "
            f"(accuracy {full['lomo_accuracy']:.1%})."
        )
    outside = []
    for name in features:
        low, high = ranges.get(name, (None, None))
        if low is not None and not low <= supplied[name] <= high:
            outside.append(f"{_LABELS[name]} {supplied[name]:g} (trained on {low:g} to {high:g})")
    if outside:
        caveats.append(
            "OUTSIDE TRAINING RANGE, so the stated accuracy does not apply: "
            + "; ".join(outside) + "."
        )
    caveats.append("Measure tapped density and re-run for a definitive classification.")
    return caveats


def classify_ml(bulk_density: float, angle_of_repose: float, particle_size: float | None,
                moisture: float | None, flow_rate: float | None, bundles: dict | None,
                ranges: dict | None = None) -> FlowResult:
    validate_densities(bulk_density, None)
    if not bundles:
        raise FlowInputError(
            "No model is loaded, so flow cannot be estimated without tapped density. "
            "Measure tapped density and use the exact path instead."
        )
    supplied = {
        "Bulk_Density_g_mL": bulk_density,
        "Angle_of_Repose_deg": angle_of_repose,
        "Mean_Particle_Size_um": particle_size,
        "Moisture_Content_percent": moisture,
        "Flow_Rate_g_s": flow_rate,
    }
    tier, bundle = select_tier(supplied, bundles)
    if bundle is None:
        raise FlowInputError(
            "Not enough measurements for any available model tier. "
            "Supplying tapped density gives an exact classification."
        )
    row = [float(supplied[f]) for f in bundle["features"]]
    proba = bundle["model"].predict_proba([row])[0]
    k = int(max(range(len(proba)), key=lambda i: proba[i]))
    return FlowResult(
        path="ml", predicted_class=bundle["classes"][k], poor_flow=k == 1,
        confidence=round(float(proba[k]), 3), model_version=f"{bundle['version']}/{tier}",
        basis=bundle.get("basis", "Machine-learning screening estimate."),
        caveats=_ml_caveats(tier, bundle, bundles, supplied, ranges or {}),
    )


def classify(bulk_density: float, tapped_density: float | None = None,
             angle_of_repose: float | None = None, particle_size: float | None = None,
             moisture: float | None = None, flow_rate: float | None = None,
             bundles: dict | None = None, ranges: dict | None = None) -> FlowResult:
    """Take the exact path when possible, the model only when necessary."""
    if tapped_density is not None:
        return classify_rule(bulk_density, tapped_density)
    if angle_of_repose is None:
        raise FlowInputError(
            "Supply either tapped density, which gives an exact pharmacopoeial class, "
            "or angle of repose, which gives a screening estimate."
        )
    return classify_ml(bulk_density, angle_of_repose, particle_size, moisture, flow_rate,
                       bundles, ranges)
