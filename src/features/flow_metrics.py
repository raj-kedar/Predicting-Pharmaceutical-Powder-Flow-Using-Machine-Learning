"""USP <1174> flow metrics. Pure functions with no I/O."""
from __future__ import annotations

USP_CLASSES = ["Excellent", "Good", "Fair", "Passable", "Poor", "Very poor", "Very, very poor"]
CARR_EDGES = [10.0, 15.0, 20.0, 25.0, 31.0, 37.0]
HAUSNER_EDGES = [1.11, 1.18, 1.25, 1.34, 1.45, 1.59]

# Acceptable for manufacturing at Carr's <= 20; genuinely poor at Carr's >= 25.
# 20 < Carr's < 25 is neither, which is why these are two separate flags.
ACCEPTABLE_MAX_CARR = 20.0
POOR_MIN_CARR = 25.0

# Removes binary floating-point noise before comparing with a band edge. Bulk 0.45,
# tapped 0.60 is exactly 25% but evaluates to 24.999999999999993, which would miss
# the poor-flow threshold; bulk 0.09, tapped 0.10 is exactly 10% but evaluates above it.
_EDGE_DECIMALS = 9


def _clean(value: float) -> float:
    return round(value, _EDGE_DECIMALS)


def band(value: float, edges: list[float]) -> int:
    value = _clean(value)
    for index, edge in enumerate(edges):
        if value <= edge:
            return index
    return len(edges)


def carrs_index(bulk_density: float, tapped_density: float) -> float:
    return _clean((tapped_density - bulk_density) / tapped_density * 100.0)


def hausner_ratio(bulk_density: float, tapped_density: float) -> float:
    return _clean(tapped_density / bulk_density)


def is_poor_flow(carr_index: float) -> bool:
    return _clean(carr_index) >= POOR_MIN_CARR


def is_acceptable(carr_index: float) -> bool:
    return _clean(carr_index) <= ACCEPTABLE_MAX_CARR
