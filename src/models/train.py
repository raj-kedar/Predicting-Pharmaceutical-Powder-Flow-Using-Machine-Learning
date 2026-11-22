"""Train the three screening tiers with leave-one-material-out validation."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.loader import load_training_data
from src.evaluation.validation import confusion, leave_one_material_out
from src.features.flow_metrics import POOR_MIN_CARR
from src.models.forest import Forest, accuracy, balanced_acc, macro_f1
from src.models.registry import tier_path, write_manifest

TIER_FEATURES = {
    "full": ["Bulk_Density_g_mL", "Angle_of_Repose_deg", "Mean_Particle_Size_um",
             "Moisture_Content_percent", "Flow_Rate_g_s"],
    "mid": ["Bulk_Density_g_mL", "Angle_of_Repose_deg", "Mean_Particle_Size_um",
            "Moisture_Content_percent"],
    "basic": ["Bulk_Density_g_mL", "Angle_of_Repose_deg"],
}
CLASSES = ["Acceptable (Carr's < 25)", "Poor flow (Carr's >= 25)"]
MODEL_SEED = 14  # the seed the published v1.1.0 figures were produced with


def train_all(data_dir: Path, out_dir: Path, version: str) -> list[dict]:
    df = load_training_data(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    groups = df.Material.values
    y = (df.Carrs_Index_percent.values >= POOR_MIN_CARR).astype(int)
    baseline = float(np.bincount(y).max() / len(y))

    def make() -> Forest:
        return Forest(n=40, max_depth=6, seed=MODEL_SEED)

    summary = []
    for tier, features in TIER_FEATURES.items():
        X = df[features].values
        pred = leave_one_material_out(make, X, y, groups)
        cm = confusion(y, pred)
        tn, fp, fn, tp = cm.ravel()
        metrics = {
            "lomo_accuracy": accuracy(y, pred),
            "lomo_balanced_acc": balanced_acc(y, pred),
            "lomo_macro_f1": macro_f1(y, pred),
            "lomo_sensitivity": float(tp / (tp + fn)),
            "lomo_specificity": float(tn / (tn + fp)),
        }
        bundle = {
            "version": version, "task": "poor_flow", "tier": tier,
            "model": make().fit(X, y, 2), "features": features, "classes": CLASSES,
            "n_materials": int(df.Material.nunique()), "n_rows": int(len(df)), **metrics,
            "majority_baseline": baseline, "confusion_matrix": cm.tolist(),
            "validation": "leave-one-material-out; every test material unseen",
            "basis": (f"Detects powders whose compressibility indicates genuinely problematic "
                      f"flow (Carr's index >= {POOR_MIN_CARR:.0f}). Tier '{tier}' uses "
                      f"{len(features)} measurement(s)."),
            "excluded_features": ["Carrs_Index_percent", "Hausners_Ratio"],
            "excluded_reason": ("Algebraic functions of bulk and tapped density; the target is "
                                "a band of Carr's index, so using them would be circular."),
        }
        path = tier_path(out_dir, tier, version)
        with open(path, "wb") as fh:
            pickle.dump(bundle, fh)
        card = {k: v for k, v in bundle.items() if k != "model"}
        path.with_suffix(".card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
        summary.append({"tier": tier, "n_features": len(features), **metrics,
                        "baseline": baseline})

    pd.DataFrame(summary).to_csv(out_dir / f"tier_summary_v{version}.csv", index=False)
    write_manifest(out_dir, version, df)
    return summary
