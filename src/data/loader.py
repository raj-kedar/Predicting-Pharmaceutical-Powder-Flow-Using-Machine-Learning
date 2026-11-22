"""Load the compiled training dataset from data/raw (read-only)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.models.registry import FEATURES

DATASETS = ("flowability_excipients_600_dataset.csv", "flowability_api_granules_600_dataset.csv")
REQUIRED = {"Material", "Tapped_Density_g_mL", "Carrs_Index_percent", *FEATURES}


def load_training_data(data_dir: Path) -> pd.DataFrame:
    frames = []
    for name in DATASETS:
        path = data_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Missing input dataset: {path}")
        frames.append(pd.read_csv(path))
    df = pd.concat(frames, ignore_index=True)

    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing columns: {sorted(missing)}")
    invalid = df.Tapped_Density_g_mL < df.Bulk_Density_g_mL
    return df.loc[~invalid].reset_index(drop=True)
