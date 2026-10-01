from __future__ import annotations
"""UAI baseline runner (Phase M17): execute suites, save results.

Usage (from the HERCULE repo root)::

    python -m evaluation.run_baseline uai_core golden_v1

Writes ``evaluation/results/baseline/<suite>.json``,
``environment.json``, and prints the HERCULE Evaluation Scorecard
per suite. Hermetic adapter: mock backend, isolated tmp state —
production stores are never touched. Numbers are measured, never
invented; external benchmarks are out of scope here by design.
"""

import json
import platform
import sys
from pathlib import Path
from typing import List

RESULTS_DIR = Path(__file__).resolve().parent / "results" / "baseline"


def _environment(adapter, suites: List[str]) -> dict:
    import evaluation.framework.version as _version

    try:
        app_version = _version.app_version()
    except Exception:
        app_version = "UNKNOWN"
    return {
        "hercule_version": app_version,
        "python_version": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "model": adapter.default_model(),
        "provider": adapter.default_provider(),
        "suites": list(suites),
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
    }


def _clean_workspace() -> None:
    """Remove prior golden-run artifacts so file tasks start unambiguous."""
    import os

    for name in os.listdir("."):
        if name.startswith("eval_golden_") and os.path.isfile(name):
            try:
                os.remove(name)
            except OSError:
                pass


def main(argv: List[str]) -> int:
    from evaluation.framework.adapters import HermeticEvalAdapter
    from evaluation.framework.config import EvalConfig
    from evaluation.framework.registry import suite_tasks
    from evaluation.framework.reliability import repeat_stats
    from evaluation.framework.reporting import (
        report_json, scorecard, scorecard_markdown)

    suites = [a for a in argv[1:] if not a.startswith("-")] or ["uai_core"]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _clean_workspace()
    adapter = HermeticEvalAdapter()
    try:
        (RESULTS_DIR / "environment.json").write_text(
            json.dumps(_environment(adapter, suites), indent=2), encoding="utf-8")
        code = 0
        for suite_id in suites:
            tasks = suite_tasks(suite_id)
            run = __import__("evaluation.framework.runner", fromlist=["EvaluationRunner"]).EvaluationRunner(
                adapter, EvalConfig(live=False)).run_suite(tasks, scope=suite_id)
            payload = report_json(run)
            payload["reliability"] = repeat_stats(run.results)
            (RESULTS_DIR / f"{suite_id}.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8")
            text = scorecard(run, reliability=payload["reliability"])
            print(text)
            print()
            (RESULTS_DIR / f"{suite_id}.md").write_text(
                scorecard_markdown(run, reliability=payload["reliability"]),
                encoding="utf-8")
            counts = run.counts
            if counts.get("error", 0) or counts.get("timeout", 0):
                code = 1
        return code
    finally:
        adapter.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
