"""Fetch a pinned official ARC-AGI-2 training snapshot and freeze a split.

Sparse checkout is deliberately limited to data/training. Evaluation tasks
are not fetched or opened by this development-data command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

OFFICIAL_URL = "https://github.com/arcprize/ARC-AGI-2.git"
PINNED_COMMIT = "f3283f727488ad98fe575ea6a5ac981e4a188e49"
SPLIT_SEED = "HERCULE-ARC-AGI-2-internal-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def prepare(root: Path, commit: str = PINNED_COMMIT) -> dict:
    root = root.resolve()
    data_root = root / "data" / "arc_agi2"
    source = data_root / "_official_source"
    tasks_root = data_root / "public_training"
    data_root.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        run("git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
            "--no-checkout", OFFICIAL_URL, str(source))
    actual_remote = run("git", "remote", "get-url", "origin", cwd=source)
    if actual_remote.rstrip("/").lower() != OFFICIAL_URL.lower():
        raise RuntimeError(f"unexpected ARC source remote: {actual_remote}")
    run("git", "sparse-checkout", "set", "data/training", cwd=source)
    run("git", "fetch", "--depth", "1", "origin", commit, cwd=source)
    run("git", "checkout", "--detach", "FETCH_HEAD", cwd=source)
    resolved = run("git", "rev-parse", "HEAD", cwd=source)
    if resolved != commit:
        raise RuntimeError(f"official source pin mismatch: {resolved} != {commit}")

    source_tasks = source / "data" / "training"
    files = sorted(source_tasks.glob("*.json"))
    if not files:
        raise RuntimeError("official training directory is empty")
    tasks_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for source_file in files:
        target = tasks_root / source_file.name
        if not target.exists() or sha256(target) != sha256(source_file):
            shutil.copy2(source_file, target)
        rows.append({"file": target.name, "sha256": sha256(target),
                     "split_key": hashlib.sha256(
                         f"{SPLIT_SEED}:{target.name}".encode()).hexdigest()})
    ordered = sorted(rows, key=lambda item: item["split_key"])
    validation_count = max(1, round(len(ordered) * 0.2))
    validation = ordered[:validation_count]
    development = ordered[validation_count:]
    manifest = {
        "dataset": "ARC-AGI-2 official public training split",
        "source": OFFICIAL_URL,
        "commit": commit,
        "split_seed": SPLIT_SEED,
        "split_method": "sort by sha256(seed + task filename); first 20% validation",
        "fetched_utc": datetime.now(timezone.utc).isoformat(),
        "task_count": len(rows),
        "development_count": len(development),
        "validation_count": len(validation),
        "training_tasks": [{"file": x["file"], "sha256": x["sha256"]}
                           for x in development],
        "validation_tasks": [{"file": x["file"], "sha256": x["sha256"]}
                             for x in validation],
    }
    manifest_path = data_root / "internal_split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"manifest": str(manifest_path), "task_count": len(rows),
            "development_count": len(development),
            "validation_count": len(validation), "commit": commit}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--commit", default=PINNED_COMMIT)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.commit), indent=2))

