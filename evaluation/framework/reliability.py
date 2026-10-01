from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Reliability (UAI Phase M5/M8)
Author: Heeran Paul
License: MIT
--------------------------------------------

Repeated-run statistics over recorded results: success rate,
pass@k, pass^k, latency/step variance. Pure functions over
numbers — never model calls, never fabricated samples. Small
sample sizes are labeled, not hidden.
"""

import math
import statistics
from typing import Any, Dict, List


def base_task_id(task_id: str) -> str:
    """Strip the ``#rN`` repeat suffix the runner appends."""
    head, marker, _ = str(task_id or "").partition("#r")
    return head if marker else str(task_id or "")


def group_repeats(results: List[Any]) -> Dict[str, List[Any]]:
    """Group TaskResults (or dicts) by base task id, preserving order."""
    groups: Dict[str, List[Any]] = {}
    for result in results or []:
        tid = result.task_id if hasattr(result, "task_id") else result.get("task_id", "")
        groups.setdefault(base_task_id(tid), []).append(result)
    return groups


def _passed(result: Any) -> bool:
    outcome = result.outcome if hasattr(result, "outcome") else result.get("outcome", "")
    value = getattr(outcome, "value", outcome)
    return str(value).lower() == "passed"


def _latency(result: Any) -> float:
    value = result.latency_ms if hasattr(result, "latency_ms") else result.get("latency_ms", 0.0)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def pass_at_k(passes: int, total: int, k: int) -> float:
    """Unbiased pass@k estimator; 1.0/0.0 at the degenerate edges."""
    if total <= 0 or k <= 0:
        return 0.0
    if passes <= 0:
        return 0.0
    if passes >= total:
        return 1.0
    if k >= total:
        return 1.0
    try:
        missed = math.comb(total - passes, k) / math.comb(total, k)
    except ValueError:
        return 0.0
    return round(1.0 - missed, 3)


def repeat_stats(results: List[Any]) -> Dict[str, Any]:
    """Per-task repeat statistics for one suite run's results."""
    groups = group_repeats(results)
    per_task: Dict[str, Any] = {}
    for task_id, items in groups.items():
        n = len(items)
        passed = sum(1 for r in items if _passed(r))
        latencies = [_latency(r) for r in items]
        entry: Dict[str, Any] = {
            "runs": n,
            "passed": passed,
            "success_rate": round(passed / n, 3) if n else 0.0,
            "pass_at_1": round(passed / n, 3) if n else 0.0,
            "pass_at_k_full": pass_at_k(passed, n, n),
            "pass_pow_k": round((passed / n) ** n, 3) if n else 0.0,
            "latency_mean_ms": round(statistics.fmean(latencies), 1) if latencies else 0.0,
            "latency_stdev_ms": (round(statistics.stdev(latencies), 1)
                                 if len(latencies) >= 2 else 0.0),
            "small_sample": n < 5,
        }
        per_task[task_id] = entry
    rates = [e["success_rate"] for e in per_task.values()]
    summary = {
        "tasks": len(per_task),
        "repeated_tasks": sum(1 for e in per_task.values() if e["runs"] > 1),
        "mean_success_rate": round(statistics.fmean(rates), 3) if rates else 0.0,
        "tasks_all_passed": sum(1 for e in per_task.values()
                                if e["runs"] and e["passed"] == e["runs"]),
        "tasks_all_failed": sum(1 for e in per_task.values() if e["passed"] == 0),
    }
    return {"per_task": per_task, "summary": summary}
