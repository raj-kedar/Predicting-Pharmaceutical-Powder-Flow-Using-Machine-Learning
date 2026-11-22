"""Record checksums for the current model files. Run only for files you trust."""
from __future__ import annotations

from src.config import load_settings
from src.data.loader import load_training_data
from src.models.registry import write_manifest


def main() -> None:
    settings = load_settings()
    frame = load_training_data(settings.raw_data_dir)
    print(f"Wrote {write_manifest(settings.model_dir, settings.model_version, frame)}")


if __name__ == "__main__":
    main()
