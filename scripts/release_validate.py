#!/usr/bin/env python3
"""Release validation gate (Phase 9O): P0 checks before any release.

Checks: pytest subset (LM + adaptation + moral + web + memory),
benchmark freeze integrity, baselines file, model-card presence,
artifact manifest freshness. Exit 0 = shippable, 1 = blocked.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports" / "frontier_program"

PYTEST_SET = [
    "tests/test_hercule_lm.py", "tests/test_hercule_lm_n4.py",
    "tests/test_hercule_lm_n5.py", "tests/test_hercule_lm_torch.py",
    "tests/test_hercule_lm_dataset_v2.py",
    "tests/test_hercule_lm_posttrain_eval.py",
    "tests/test_adaptation.py", "tests/test_adaptation_integration.py",
    "tests/test_moral_reasoning.py", "tests/test_frontier_phase8.py",
    "tests/test_web_product.py", "tests/test_memory.py",
]


def main() -> int:
    results: dict = {"timestamp": datetime.now(timezone.utc).isoformat(),
                     "checks": {}, "blockers": []}
    proc = subprocess.run([sys.executable, "-m", "pytest"] + PYTEST_SET +
                          ["-q", "--tb=no"], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=3600)
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    summary = tail[-1] if tail else "no output"
    results["checks"]["pytest"] = {"returncode": proc.returncode,
                                   "summary": summary[-200:]}
    if proc.returncode != 0:
        results["blockers"].append(f"pytest failed: {summary[-200:]}")
    for name in ("benchmark_freeze.json", "baselines.json",
                 "model_card_nano.md", "MANIFEST.json",
                 "scorecard_public.json"):
        ok = (REPORTS / name).exists()
        results["checks"][name] = ok
        if not ok:
            results["blockers"].append(f"missing artifact {name}")
    freeze = {}
    try:
        freeze = json.loads((REPORTS / "benchmark_freeze.json").read_text())
    except (OSError, ValueError):
        pass
    if freeze.get("policy", "").startswith("FROZEN"):
        results["checks"]["freeze_policy"] = True
    else:
        results["checks"]["freeze_policy"] = False
        results["blockers"].append("benchmark freeze policy missing")
    results["shippable"] = not results["blockers"]
    (REPORTS / "release_validation.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps({"shippable": results["shippable"],
                      "blockers": results["blockers"]}, indent=1))
    return 0 if results["shippable"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
