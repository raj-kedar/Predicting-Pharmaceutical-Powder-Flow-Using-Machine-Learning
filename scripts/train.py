"""Retrain all tiers. Usage: python -m scripts.train [--out DIR]"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.config import load_settings
from src.models.train import train_all


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=settings.model_dir)
    args = parser.parse_args()
    print(f"{'tier':<7}{'acc':>8}{'balanced':>10}{'sens':>8}{'spec':>8}")
    for row in train_all(settings.raw_data_dir, args.out, settings.model_version):
        print(f"{row['tier']:<7}{row['lomo_accuracy']:>8.3f}{row['lomo_balanced_acc']:>10.3f}"
              f"{row['lomo_sensitivity']:>8.3f}{row['lomo_specificity']:>8.3f}")
    print(f"Saved models and manifest to {args.out}")


if __name__ == "__main__":
    main()
