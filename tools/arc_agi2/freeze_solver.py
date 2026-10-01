"""Write a one-way solver hash record before the single public evaluation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.arc_agi2.benchmark import solver_digest


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(root: Path) -> dict:
    root = root.resolve()
    target = root / "artifacts" / "arc_agi2" / "solver_freeze.json"
    if target.exists():
        raise FileExistsError(f"solver is already frozen: {target}")
    score = root / "artifacts" / "arc_agi2" / "internal_validation_final.json"
    split = root / "data" / "arc_agi2" / "internal_split_manifest.json"
    if not score.is_file() or not split.is_file():
        raise FileNotFoundError("freeze requires final internal score and split manifest")
    record = {"solver_sha256": solver_digest(root),
              "internal_score_sha256": sha256(score),
              "internal_split_manifest_sha256": sha256(split),
              "benchmark_harness_sha256": sha256(root / "tools" / "arc_agi2" / "benchmark.py"),
              "public_data_preparation_sha256": sha256(
                  root / "tools" / "arc_agi2" / "prepare_public_evaluation.py"),
              "frozen_utc": datetime.now(timezone.utc).isoformat(),
              "sources": ["arc_reasoning/*.py", "agents/arc_reasoning_agent.py",
                          "tools/arc_agi2/benchmark.py",
                          "tools/arc_agi2/prepare_public_evaluation.py",
                          "internal_validation_final.json",
                          "internal_split_manifest.json"]}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(freeze(args.root), indent=2))
