from __future__ import annotations
"""A/B evaluation: BASELINE vs ADAPTIVE (6U §14).

Same task set, same tools, same budgets; only the learning loop
differs. Reports success, retries, latency, tool calls, recovery —
never claims adaptation wins without the measured delta.
"""

import time
from typing import Any, Callable, Dict, List

from cognition.adaptation.executor import AdaptiveExecutor
from cognition.adaptation.metrics import LearningMetrics


def _baseline_run(task: Dict[str, Any], act, verify) -> Dict[str, Any]:
    t0 = time.perf_counter()
    action = {"step_id": "s1", "action": task["goal"], "tool": "",
              "input": {}}
    try:
        result = act(dict(action)) or {}
    except Exception as exc:
        result = {"observation": f"error: {exc}"}
    try:
        verdict = verify(dict(action), dict(result)) or {}
    except Exception as exc:
        verdict = {"verified": False, "detail": str(exc)}
    return {"task_id": task["id"], "verified": bool(verdict.get("verified")),
            "retries": 0, "attempts": [{"action": action,
                                        "observation": str(result.get("observation", ""))}],
            "wall_s": round(time.perf_counter() - t0, 3)}


def compare(tasks: List[Dict[str, Any]], act, verify,
            executor_factory: Callable[[], AdaptiveExecutor],
            family: str = "general") -> Dict[str, Any]:
    """Run BASELINE then ADAPTIVE over the same tasks. Returns deltas."""
    metrics = LearningMetrics()
    base_ok, adapt_ok, base_t, adapt_t = 0, 0, 0.0, 0.0
    base_retries, adapt_retries = 0, 0
    for task in tasks:
        b = _baseline_run(task, act, verify)
        base_ok += b["verified"]
        base_t += b["wall_s"]
        metrics.record(family + ":baseline", b)
        ex = executor_factory()
        a = ex.run(task["id"], task["goal"], act, verify,
                   plan=task.get("plan"), alternatives=task.get("alternatives"),
                   environment=task.get("environment"))
        adapt_ok += a["verified"]
        adapt_t += a.get("wall_s", 0.0)
        base_retries += b["retries"]
        adapt_retries += a.get("retries", 0)
        metrics.record(family + ":adaptive", a)
    n = max(1, len(tasks))
    return {
        "tasks": len(tasks),
        "baseline": {"success_rate": round(base_ok / n, 3),
                     "mean_wall_s": round(base_t / n, 3),
                     "mean_retries": round(base_retries / n, 2)},
        "adaptive": {"success_rate": round(adapt_ok / n, 3),
                     "mean_wall_s": round(adapt_t / n, 3),
                     "mean_retries": round(adapt_retries / n, 2)},
        "delta_success": round((adapt_ok - base_ok) / n, 3),
        "verdict": ("adaptive-better" if adapt_ok > base_ok else
                    "baseline-better" if base_ok > adapt_ok else "tie"),
        "metrics": metrics.report(),
    }
