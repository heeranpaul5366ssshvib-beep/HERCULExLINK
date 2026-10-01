"""Paired v3-versus-relation candidate score on one frozen dev sample."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path


def run(root: Path, candidate: str, output: Path) -> dict:
    root = root.resolve()
    snapshot = root / "artifacts" / "arc_agi2" / "solver_v3_snapshot"
    sys.path.insert(0, str(root))
    if candidate == "baseline-v3":
        sys.path.insert(0, str(snapshot))
        benchmark_path = snapshot / "benchmark.py"
    else:
        benchmark_path = root / "tools" / "arc_agi2" / "benchmark.py"
    namespace = runpy.run_path(str(benchmark_path))
    evaluate = namespace["evaluate_internal"]
    report = evaluate(root, "training_tasks",
                      "relation_copy_discovery_split_manifest.json")
    report["experiment"] = "relation-conditioned copy/place discovery"
    report["candidate"] = candidate
    report["solver_sha256"] = (
        "67a4b28a2e2146a70bcdbd1913f615ab210532352b44d0217ce38e5f576ad55d"
        if candidate == "baseline-v3" else report["solver_sha256"])
    report["frozen_public_evaluation_touched"] = False
    report["frozen_128_task_holdout_touched"] = False
    output = output if output.is_absolute() else root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument("--candidate", choices=("baseline-v3", "relation-v1"),
                        required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root, args.candidate, args.output)
    print(json.dumps({key: report.get(key) for key in (
        "candidate", "solver_sha256", "task_count", "solved_tasks",
        "top1_test_outputs", "pass2_test_outputs", "test_output_count",
        "elapsed_seconds", "hypothesis_coverage")}, indent=2))
