"""Physical plausibility checks shared by the engine and the API."""
from __future__ import annotations

import math


class FlowInputError(ValueError):
    """The supplied measurements are impossible or insufficient."""


def validate_densities(bulk_density: float | None, tapped_density: float | None) -> None:
    if bulk_density is None or not math.isfinite(bulk_density) or bulk_density <= 0:
        raise FlowInputError("Bulk density must be a finite number greater than zero.")
    if bulk_density > 5:
        raise FlowInputError(
            "A bulk density above 5 g/mL is not plausible for a pharmaceutical powder. "
            "Check the units: this field expects g/mL."
        )
    if tapped_density is None:
        return
    if not math.isfinite(tapped_density) or tapped_density <= 0:
        raise FlowInputError("Tapped density must be a finite number greater than zero.")
    if tapped_density > 5:
        raise FlowInputError("A tapped density above 5 g/mL is not plausible. Check the units.")
    if tapped_density < bulk_density:
        raise FlowInputError(
            "Tapped density is below bulk density, which is physically impossible because "
            "tapping cannot loosen packing. Check which reading went into which field."
        )
