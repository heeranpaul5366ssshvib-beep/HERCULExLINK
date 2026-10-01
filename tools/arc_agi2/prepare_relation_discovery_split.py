"""Freeze a new iterative discovery sample from the unused 512-task pool."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


SEED = "HERCULE-ARC-AGI-2-relation-copy-discovery-v1"


def freeze(root: Path, count: int = 128) -> dict:
    root = root.resolve()
    data_root = root / "data" / "arc_agi2"
    source_path = root / "artifacts" / "arc_agi2" / \
        "hypothesis_discovery_split_manifest.json"
    output_path = data_root / "relation_copy_discovery_split_manifest.json"
    if output_path.exists():
        raise FileExistsError(f"discovery split already frozen: {output_path}")
    source = json.loads(source_path.read_text("utf-8"))
    reserve = {row["file"] for row in source["validation_tasks"]}
    development = list(source["training_tasks"])
    if len(development) != 512 or any(row["file"] in reserve for row in development):
        raise ValueError("source is not the expected disjoint 512-task development pool")
    if not 16 <= count < len(development):
        raise ValueError("discovery sample count must be at least 16 and below 512")
    task_root = data_root / "public_training"
    keyed = []
    for row in development:
        path = task_root / row["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            raise ValueError(f"development task hash changed: {row['file']}")
        keyed.append({**row, "split_key": hashlib.sha256(
            f"{SEED}:{row['file']}".encode()).hexdigest()})
    keyed.sort(key=lambda row: row["split_key"])
    discovery = keyed[:count]
    remaining = keyed[count:]
    manifest = {
        "dataset": source["dataset"], "source": source["source"],
        "commit": source["commit"], "source_manifest": source_path.name,
        "source_manifest_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_pool": "512 unused discovery-development tasks only; excludes frozen 128-task holdout",
        "split_seed": SEED,
        "split_method": "sort unused development tasks by sha256(seed + filename); first count selected",
        "task_count": len(development), "discovery_count": len(discovery),
        "remaining_development_count": len(remaining),
        "frozen_holdout_used": False,
        "training_tasks": [{"file": row["file"], "sha256": row["sha256"]}
                           for row in discovery],
        "validation_tasks": [{"file": row["file"], "sha256": row["sha256"]}
                             for row in remaining],
    }
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"manifest": str(output_path),
            "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "discovery_count": len(discovery),
            "remaining_development_count": len(remaining),
            "seed": SEED}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--count", type=int, default=128)
    args = parser.parse_args()
    print(json.dumps(freeze(args.root, args.count), indent=2))
