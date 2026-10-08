"""Smoke test: required project folders exist."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "data/raw", "data/metadata", "notebooks", "src", "models", "results",
    "app", "api", "deployment/aws", "deployment/azure", "config", "docs", "reports",
]


def test_required_folders_exist():
    missing = [d for d in REQUIRED if not (ROOT / d).is_dir()]
    assert not missing, f"Missing folders: {missing}"
