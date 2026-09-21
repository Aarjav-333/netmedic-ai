"""Generate synthetic healthy telemetry and (re)train the Isolation Forest.

Usage (from repo root):
    cd backend && python ../scripts/train_detector.py [--save-dataset]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.detection.trainer import DATASET_PATH, MODEL_PATH, train_and_save  # noqa: E402
from app.logging_config import configure_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-dataset", action="store_true", help=f"also write {DATASET_PATH}")
    args = parser.parse_args()
    configure_logging("INFO")
    _, metadata = train_and_save(save_dataset=args.save_dataset)
    print(f"model:     {MODEL_PATH}")
    print(f"samples:   {metadata.n_samples}")
    print(f"threshold: {metadata.threshold:.4f}  severity span: {metadata.severity_span:.4f}")


if __name__ == "__main__":
    main()
