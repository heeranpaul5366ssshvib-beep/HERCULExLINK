"""Freeze a fresh internal holdout from the unused official training tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


FRESH_SEED = "HERCULE-ARC-AGI-2-object-copy-fresh-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root: Path, validation_fraction: float = 0.2) -> dict:
    root = root.resolve()
    data_root = root / "data" / "arc_agi2"
    source_path = data_root / "internal_split_manifest.json"
    output_path = data_root / "fresh_copy_split_manifest.json"
    if output_path.exists():
        raise FileExistsError(f"fresh split already frozen: {output_path}")
    if not 0.05 <= validation_fraction <= 0.5:
        raise ValueError("validation fraction must be between 0.05 and 0.5")
    source = json.loads(source_path.read_text("utf-8"))
    development = list(source["training_tasks"])
    old_validation = {row["file"] for row in source["validation_tasks"]}
    if len(development) != 800 or any(row["file"] in old_validation
                                      for row in development):
        raise ValueError("source is not the expected disjoint 800-task development pool")
    task_root = data_root / "public_training"
    rows = []
    for row in development:
        task_path = task_root / row["file"]
        digest = sha256(task_path)
        if digest != row["sha256"]:
            raise ValueError(f"development task changed: {row['file']}")
        rows.append({"file": row["file"], "sha256": digest,
                     "split_key": hashlib.sha256(
                         f"{FRESH_SEED}:{row['file']}".encode()).hexdigest()})
    ordered = sorted(rows, key=lambda row: row["split_key"])
    validation_count = round(len(ordered) * validation_fraction)
    validation, discovery = ordered[:validation_count], ordered[validation_count:]
    manifest = {
        "dataset": source["dataset"],
        "source": source["source"],
        "commit": source["commit"],
        "source_internal_split_manifest_sha256": sha256(source_path),
        "source_pool": "previous 800-task development pool only",
        "split_seed": FRESH_SEED,
        "split_method": "sort by sha256(seed + task filename); first 20% fresh validation",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "task_count": len(rows),
        "development_count": len(discovery),
        "validation_count": len(validation),
        "training_tasks": [{"file": row["file"], "sha256": row["sha256"]}
                           for row in discovery],
        "validation_tasks": [{"file": row["file"], "sha256": row["sha256"]}
                             for row in validation],
    }
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"manifest": str(output_path), "manifest_sha256": sha256(output_path),
            "task_count": len(rows), "development_count": len(discovery),
            "validation_count": len(validation), "seed": FRESH_SEED,
            "source_commit": source["commit"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(prepare(args.root), indent=2))
