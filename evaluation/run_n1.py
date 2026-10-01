from __future__ import annotations
"""Phase N1 real-model baseline (EVALUATION ONLY, no routing changes).

Runs the 5 UAI suites against the REAL model path (llama3.2:3b
default; mode-based routing may resolve other installed models —
measured, never overridden). Process-lifetime tmp isolation +
fail-closed guard. Fails closed on production-state change.

Usage (repo root)::

    python -m evaluation.run_n1 uai_core uai_research
    python -m evaluation.run_n1 uai_skills uai_safety
    python -m evaluation.run_n1 golden_v1

Writes ``evaluation/results/phase_n1_<run_id>_<suite>.{json,md}``
plus a combined ``phase_n1_<run_id>_summary.md``.
"""

import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

MODEL = "llama3.2:3b"
PROVIDER = "ollama"


def _resolve_model() -> tuple:
    """Honor preset MODEL/PROVIDER env (N2 builtin runs); else N1 defaults."""
    import os as _os

    return (_os.environ.get("HERCULE_N1_MODEL", MODEL),
            _os.environ.get("HERCULE_N1_PROVIDER", PROVIDER))

PROD_STORES = [
    "data/memory/experiences.json",
    "data/memory/hercule_memory.json",
    "data/skills/skills.json",
    "data/tasks.json",
    "data/world/hercule_world.json",
]


def _snapshot() -> Dict[str, Dict[str, Any]]:
    snap = {}
    for rel in PROD_STORES:
        path = Path(rel)
        snap[rel] = {"present": path.exists(),
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "",
                     "bytes": path.stat().st_size if path.exists() else 0}
    return snap


def _pct(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(pct * (len(ordered) - 1)))))]


def _stats(latencies: List[float]) -> Dict[str, float]:
    if not latencies:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0,
                "min": 0.0, "max": 0.0, "n": 0}
    return {"mean": round(statistics.fmean(latencies), 1),
            "median": round(statistics.median(latencies), 1),
            "p95": round(_pct(latencies, 0.95), 1),
            "p99": round(_pct(latencies, 0.99), 1),
            "min": round(min(latencies), 1),
            "max": round(max(latencies), 1),
            "n": len(latencies)}


def main(argv: List[str]) -> int:
    suites = [a for a in argv[1:] if not a.startswith("-")]
    if not suites:
        print("usage: python -m evaluation.run_n1 <suite> [suite...]")
        return 3
    model, provider = _resolve_model()
    run_id = f"n1-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    before = _snapshot()

    state_root = Path(tempfile.mkdtemp(prefix="hercule-n1-"))
    (state_root / "memory").mkdir(parents=True, exist_ok=True)
    os.environ["HERCULE_DEFAULT_MODEL"] = model
    if provider == "builtin":
        os.environ["HERCULE_MODEL_PROVIDER"] = "builtin"
    os.environ["HERCULE_ALLOW_MOCK"] = "0"
    os.environ["HERCULE_TASK_STORE"] = ":memory:"
    os.environ["HERCULE_MEMORY_DIR"] = str(state_root / "memory")
    os.environ["HERCULE_EXPERIENCE_STORE"] = str(state_root / "memory" / "experiences.json")
    os.environ["HERCULE_SKILLS_STORE"] = str(state_root / "skills.json")
    os.environ["HERCULE_WORLD_PATH"] = str(state_root / "world.json")
    os.environ["HERCULE_TEST_GUARD"] = "1"
    os.environ["HERCULE_TEST_STATE_DIR"] = str(state_root)

    from evaluation.framework.adapters import RuntimeEvalAdapter
    from evaluation.framework.config import EvalConfig
    from evaluation.framework.registry import suite_tasks
    from evaluation.framework.runner import EvaluationRunner
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    models = services.get("models")
    try:
        if provider == "builtin":
            from models.builtin import model_manager as _store

            installed = [m["id"] for m in _store.list_installed()]
        else:
            installed = list(models.installed_ollama_models() or [])
    except Exception as exc:
        installed = []
        print(f"BLOCKED: model discovery failed: {exc}")
        return 2
    if model not in installed:
        print(f"BLOCKED: {model} not installed (found: {installed})")
        return 2
    default_model = str(getattr(models, "default_model", ""))
    default_host = str(getattr(models, "ollama_host", ""))
    default_timeout = getattr(models, "ollama_timeout_s", "UNKNOWN")

    adapter = RuntimeEvalAdapter(services)
    all_results: List[Dict[str, Any]] = []
    suite_files: List[str] = []
    code = 0
    try:
        for suite_id in suites:
            tasks = suite_tasks(suite_id)
            run = EvaluationRunner(adapter, EvalConfig(live=False)).run_suite(
                tasks, scope=suite_id)
            payload = {
                "phase": "N1", "run_id": run_id, "suite": suite_id,
                "date_time": datetime.now(timezone.utc).isoformat(),
                "model_default": default_model, "provider": PROVIDER,
                "ollama_host": default_host, "ollama_timeout_s": default_timeout,
                "temperature": "UNKNOWN (server default applies)",
                "mock_used": False,
                "report": run.as_dict(),
            }
            name = f"phase_n1_{run_id}_{suite_id}.json"
            (results_dir / name).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            suite_files.append(name)
            counts = run.counts
            print(f"{suite_id}: {counts.get('passed', 0)}/{len(run.results)} "
                  f"failed={counts.get('failed', 0)} error={counts.get('error', 0)} "
                  f"timeout={counts.get('timeout', 0)}")
            if counts.get("error", 0) or counts.get("timeout", 0):
                code = 1
            all_results.extend(run.as_dict()["results"])
    finally:
        try:
            adapter.close()
        except Exception:
            pass

    after = _snapshot()
    changed = [rel for rel in PROD_STORES if before.get(rel) != after.get(rel)]
    summary = _summarize(run_id, suites, all_results, default_model, before, after, changed)
    (results_dir / f"phase_n1_{run_id}_summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    if changed:
        print("PRODUCTION_STATE_MODIFIED:", changed)
        return 2
    return code


def _summarize(run_id: str, suites: List[str], results: List[Dict[str, Any]],
               default_model: str, before: dict, after: dict, changed: list) -> str:
    by_model: Dict[str, List[Dict[str, Any]]] = {}
    by_mode: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        trace = result.get("trace") or {}
        model = trace.get("decision_model", "") or "UNKNOWN"
        mode = trace.get("reasoning_mode", "") or "UNKNOWN"
        by_model.setdefault(model, []).append(result)
        by_mode.setdefault(mode, []).append(result)

    lines = [f"# PHASE N1 ({run_id})", "",
             f"Suites: {', '.join(suites)}",
             f"Default model: {default_model} (ollama)", ""]
    lines.append("## By resolved model (measured, not ranked)")
    for model, items in sorted(by_model.items()):
        passed = sum(1 for r in items if r["outcome"] == "passed")
        lat = _stats([r["latency_ms"] for r in items if r["latency_ms"] > 0])
        lines.append(f"- {model}: tasks={len(items)} pass={passed} "
                     f"avg={lat['mean']} p95={lat['p95']}")
    lines.append("")
    lines.append("## By reasoning mode")
    for mode, items in sorted(by_mode.items()):
        passed = sum(1 for r in items if r["outcome"] == "passed")
        lat = _stats([r["latency_ms"] for r in items if r["latency_ms"] > 0])
        lines.append(f"- {mode}: tasks={len(items)} pass={passed} "
                     f"avg={lat['mean']} p95={lat['p95']}")
    lines.append("")
    routed_away = [r for r in results
                   if (r.get("trace") or {}).get("decision_model", "") not in ("", default_model, "UNKNOWN")]
    lat_all = _stats([r["latency_ms"] for r in results if r["latency_ms"] > 0])
    lines.append(f"Routed away from default: {len(routed_away)}/{len(results)}")
    lines.append(f"Fallback internals: UNKNOWN (not exposed by run_cycle contract; "
                 f"see per-task decision_model + latency)")
    lines.append(f"Latency: mean={lat_all['mean']} median={lat_all['median']} "
                 f"p95={lat_all['p95']} p99={lat_all['p99']} "
                 f"min={lat_all['min']} max={lat_all['max']}")
    lines.append(f"Production state: {'MODIFIED: ' + str(changed) if changed else 'UNCHANGED'}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
