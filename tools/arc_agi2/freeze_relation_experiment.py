"""Freeze solver and split hashes before relation discovery scoring."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BASELINE_SHA256 = "67a4b28a2e2146a70bcdbd1913f615ab210532352b44d0217ce38e5f576ad55d"


def _solver_digest(root: Path) -> str:
    files = sorted((root / "arc_reasoning").glob("*.py"))
    files += [root / "agents" / "arc_reasoning_agent.py"]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def freeze(root: Path) -> dict:
    root = root.resolve()
    artifacts = root / "artifacts" / "arc_agi2"
    snapshot = artifacts / "solver_v3_snapshot"
    digest = hashlib.sha256()
    files = sorted((snapshot / "arc_reasoning").glob("*.py"))
    files += [snapshot / "agents" / "arc_reasoning_agent.py"]
    for path in files:
        digest.update(path.relative_to(snapshot).as_posix().encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    if digest.hexdigest() != BASELINE_SHA256:
        raise ValueError("v3 baseline snapshot does not match its recorded solver hash")
    split = root / "data" / "arc_agi2" / \
        "relation_copy_discovery_split_manifest.json"
    split_hash = hashlib.sha256(split.read_bytes()).hexdigest()
    test_file = root / "tests" / "test_arc_reasoning.py"
    freeze_path = artifacts / "relation_copy_experiment_freeze_v1.json"
    if freeze_path.exists():
        raise FileExistsError(f"experiment already frozen: {freeze_path}")
    current_hash = _solver_digest(root)
    report = {
        "experiment": "relation-conditioned object copy/place and invariance filter v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "solver_sha256": current_hash,
        "baseline_v3_solver_sha256": BASELINE_SHA256,
        "discovery_split_manifest": "relation_copy_discovery_split_manifest.json",
        "discovery_split_sha256": split_hash,
        "discovery_task_count": 128,
        "source_development_pool_remaining_after_sample": 384,
        "regression_command": "python -m pytest -p no:cacheprovider --basetemp .tmp/pytest-base tests/test_arc_reasoning.py -q",
        "regression_result": "39 passed",
        "regression_test_file_sha256": hashlib.sha256(test_file.read_bytes()).hexdigest(),
        "frozen_before_scoring": True,
        "public_evaluation_touched": False,
        "prior_128_task_holdout_touched": False,
    }
    freeze_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"path": str(freeze_path), **report}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    print(json.dumps(freeze(args.root), indent=2))
