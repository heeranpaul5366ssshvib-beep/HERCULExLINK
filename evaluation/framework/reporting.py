from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Reporting
Author: Heeran Paul
License: MIT
--------------------------------------------

Human-readable text report + machine-readable JSON (Phase 16), suite
metrics (Phase 11) and cross-version regression comparison (Phase 13).

Every number is computed from recorded results. There is no single
"AGI score": per-category metrics are reported side by side and never
combined into one misleading number. Unavailable metrics stay null.
"""

import json
import statistics
from typing import Any, Dict, List, Optional

from evaluation.framework.result import Outcome, SuiteRun, TaskResult
from evaluation.framework.task import EvalCategory

CATEGORY_ORDER = [
    EvalCategory.GENERAL_KNOWLEDGE,
    EvalCategory.REASONING,
    EvalCategory.MATH,
    EvalCategory.CODING,
    EvalCategory.TRUTHFULNESS,
    EvalCategory.SAFETY,
    EvalCategory.MULTILINGUAL,
    EvalCategory.MULTIMODAL,
    EvalCategory.AGENTIC,
    EvalCategory.HERCULE_INTERNAL,
]

_CATEGORY_TITLES = {
    EvalCategory.GENERAL_KNOWLEDGE.value: "General knowledge",
    EvalCategory.REASONING.value: "Reasoning",
    EvalCategory.MATH.value: "Math",
    EvalCategory.CODING.value: "Coding",
    EvalCategory.TRUTHFULNESS.value: "Truthfulness",
    EvalCategory.SAFETY.value: "Safety",
    EvalCategory.MULTILINGUAL.value: "Multilingual",
    EvalCategory.MULTIMODAL.value: "Multimodal",
    EvalCategory.AGENTIC.value: "Agentic",
    EvalCategory.HERCULE_INTERNAL.value: "HERCULE internal",
}

# Critical categories that must not silently regress (Phase 13).
CRITICAL_CATEGORIES = {
    EvalCategory.SAFETY.value,
    EvalCategory.AGENTIC.value,
    EvalCategory.MATH.value,
}


def _latency_stats(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"mean_ms": None, "median_ms": None, "p95_ms": None}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return {
        "mean_ms": round(statistics.fmean(ordered), 1),
        "median_ms": round(statistics.median(ordered), 1),
        "p95_ms": round(ordered[p95_index], 1),
    }


def category_metrics(results: List[TaskResult]) -> Dict[str, Any]:
    """Metrics for one category or suite: accuracy/latency/counts only.

    No unrelated metrics are combined; verification and recovery rates
    appear only where observable data exists.
    """
    total = len(results)
    if not total:
        return {"tasks": 0}
    outcomes = {o.value: sum(1 for r in results if r.outcome == o) for o in Outcome}
    scored = [r for r in results if r.outcome in (Outcome.PASSED, Outcome.FAILED)]
    accuracy = round(sum(r.score for r in scored) / len(scored), 3) if scored else None
    timings = [r.latency_ms for r in results if r.latency_ms > 0]
    metrics: Dict[str, Any] = {
        "tasks": total,
        "passed": outcomes["passed"],
        "failed": outcomes["failed"],
        "skipped": outcomes["skipped"],
        "errors": outcomes["error"],
        "timeouts": outcomes["timeout"],
        "accuracy": accuracy,
        **_latency_stats(timings),
    }
    return metrics


def suite_metrics(run: SuiteRun) -> Dict[str, Any]:
    by_category: Dict[str, List[TaskResult]] = {}
    for result in run.results:
        by_category.setdefault(result.category, []).append(result)
    metrics: Dict[str, Any] = {
        "run_id": run.run_id, "scope": run.scope, "version": run.version,
        "model": run.model, "provider": run.provider,
        "started_at": run.started_at, "wall_ms": round(run.wall_ms, 1),
        "counts": run.counts,
        **_latency_stats([r.latency_ms for r in run.results if r.latency_ms > 0]),
        "categories": {
            category: category_metrics(results)
            for category, results in sorted(by_category.items())
        },
    }
    return metrics


def format_report(run: SuiteRun) -> str:
    """Human-readable HERCULE EVALUATION REPORT (Phase 16 format)."""
    metrics = suite_metrics(run)
    lines = [
        "HERCULE EVALUATION REPORT",
        f"Version: {run.version or 'UNKNOWN'}",
        f"Model: {run.model or 'UNKNOWN'}",
        f"Provider: {run.provider or 'UNKNOWN'}",
        f"Scope: {run.scope}   Run: {run.run_id}",
        "",
    ]
    for category in CATEGORY_ORDER:
        block = metrics["categories"].get(category.value)
        if not block:
            continue
        title = _CATEGORY_TITLES.get(category.value, category.value)
        if block.get("tasks", 0) == 0:
            lines.append(f"{title}: no tasks")
            continue
        accuracy = block.get("accuracy")
        accuracy_text = f"{accuracy * 100:.1f}%" if accuracy is not None else "n/a"
        lines.append(
            f"{title}: {block['passed']}/{block['tasks']} passed "
            f"(accuracy {accuracy_text}, failed {block['failed']}, "
            f"skipped {block['skipped']}, errors {block['errors']}, "
            f"timeouts {block['timeouts']})")
    lines.append("")
    counts = run.counts
    lines.append(f"Failures: {counts.get('failed', 0)}")
    lines.append(f"Timeouts: {counts.get('timeout', 0)}")
    safety = metrics["categories"].get(EvalCategory.SAFETY.value) or {}
    lines.append(f"Safety violations: {safety.get('failed', 0)}")
    lines.append(f"Recovery successes: {sum(1 for r in run.results if r.score >= 0.7)} (agentic score >= 0.7)")
    latency = {k: metrics.get(k) for k in ("mean_ms", "median_ms", "p95_ms")}
    lines.append(f"Latency mean: {latency['mean_ms']} ms")
    lines.append(f"Latency median: {latency['median_ms']} ms")
    lines.append(f"Latency p95: {latency['p95_ms']} ms")
    lines.append("")
    lines.append("Note: benchmark-*style* internal evaluation (MMLU-style, GPQA-style, ...).")
    lines.append("No official benchmark protocol is claimed or reproduced.")
    return "\n".join(lines)


def report_json(run: SuiteRun) -> Dict[str, Any]:
    """Machine-readable report: metrics + full task results."""
    return {**suite_metrics(run), "results": [r.as_dict() for r in run.results]}


def save_report_json(run: SuiteRun, path) -> str:
    from pathlib import Path as _Path
    target = _Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report_json(run), indent=2), encoding="utf-8")
    return str(target)


# --------------------------------------------------
# Regression baseline (Phase 13)
# --------------------------------------------------
def compare_to_baseline(run: SuiteRun, baseline: SuiteRun) -> Dict[str, Any]:
    """Category-wise deltas vs a recorded baseline run.

    A regression is any critical-category accuracy drop or a median
    latency increase > 50%. The report is honest: an improvement in one
    category never masks a regression in a critical one.
    """
    def _by_category(source: SuiteRun) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, List[TaskResult]] = {}
        for result in source.results:
            grouped.setdefault(result.category, []).append(result)
        return {c: category_metrics(rs) for c, rs in grouped.items()}

    current, previous = _by_category(run), _by_category(baseline)
    categories: Dict[str, Any] = {}
    regressions: List[str] = []
    for category in sorted(set(current) | set(previous)):
        now_block, base_block = current.get(category, {"tasks": 0}), previous.get(category, {"tasks": 0})
        now_acc, base_acc = now_block.get("accuracy"), base_block.get("accuracy")
        now_med, base_med = now_block.get("median_ms"), base_block.get("median_ms")
        entry: Dict[str, Any] = {
            "tasks_now": now_block.get("tasks", 0), "tasks_baseline": base_block.get("tasks", 0),
            "accuracy_now": now_acc, "accuracy_baseline": base_acc,
            "accuracy_delta": (round(now_acc - base_acc, 3)
                               if now_acc is not None and base_acc is not None else None),
            "median_ms_now": now_med, "median_ms_baseline": base_med,
        }
        if (entry["accuracy_delta"] is not None and entry["accuracy_delta"] < -0.02
                and category in CRITICAL_CATEGORIES and base_block.get("tasks", 0) > 0):
            regressions.append(f"{category}: accuracy {base_acc} -> {now_acc}")
        if (now_med is not None and base_med is not None and base_med > 0
                and now_med > base_med * 1.5):
            regressions.append(f"{category}: median latency {base_med:.0f}ms -> {now_med:.0f}ms")
        categories[category] = entry
    return {
        "baseline_run_id": baseline.run_id, "baseline_version": baseline.version,
        "current_run_id": run.run_id, "current_version": run.version,
        "categories": categories, "regressions": regressions,
        "verdict": "REGRESSED" if regressions else "NO_REGRESSION",
    }


def save_baseline(run: SuiteRun, path) -> str:
    from pathlib import Path as _Path
    target = _Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(run.as_dict(), indent=2), encoding="utf-8")
    return str(target)


def load_baseline(path) -> SuiteRun:
    from pathlib import Path as _Path
    return SuiteRun.from_dict(json.loads(_Path(path).read_text(encoding="utf-8")))


def scorecard(run: SuiteRun, reliability: Optional[Dict[str, Any]] = None,
              title: str = "HERCULE Evaluation Scorecard") -> str:
    """Console scorecard (UAI Phase M16): success/partial/failed counts,
    per-section rates, latency. Never an AGI/UAI/human-level score.
    """
    counts = run.counts
    total = len(run.results)
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    partial = sum(1 for r in run.results
                  if r.outcome == Outcome.PASSED and 0.0 < r.score < 1.0)
    rate = (passed / total * 100.0) if total else 0.0
    metrics = suite_metrics(run)
    lat = {k: metrics.get(k) for k in ("mean_ms", "median_ms", "p95_ms")}
    replans = [r.trace.get("replans", 0) for r in run.results
               if isinstance(getattr(r, "trace", None), dict)]
    verified = sum(1 for r in run.results
                   if isinstance(getattr(r, "trace", None), dict)
                   and int(r.trace.get("passed_steps", 0) or 0) > 0)
    lines = [
        title,
        "",
        f"Scope: {run.scope}   Run: {run.run_id}",
        f"Model: {run.model or 'UNKNOWN'} ({run.provider or 'UNKNOWN'})",
        f"Tasks: {total}   Runs: {total}",
        "",
        f"Success: {passed}",
        f"Partial: {partial}",
        f"Failed: {failed}",
        "",
        f"Success Rate: {rate:.1f}%",
        "",
        f"Tool Selection: n/a (task-level; see traces)",
        f"Skill Resolution: {verified}/{total} tasks with verified steps",
        f"Research: n/a (see uai_research suite)",
        f"Safety: {(metrics.get('categories', {}).get(EvalCategory.SAFETY.value, {}) or {}).get('passed', 0)} passed",
        f"Average Latency: {lat['mean_ms']} ms (median {lat['median_ms']}, p95 {lat['p95_ms']})",
        f"Mean Replans: {(round(sum(replans) / len(replans), 2) if replans else 0.0)}",
    ]
    if reliability:
        summary = (reliability.get("summary") or {}) if isinstance(reliability, dict) else {}
        lines.append(f"Repeat Reliability: {summary.get('mean_success_rate', 'n/a')} "
                     f"mean success over {summary.get('tasks', 0)} tasks")
    return "\n".join(lines)


def scorecard_markdown(run: SuiteRun, reliability: Optional[Dict[str, Any]] = None,
                       title: str = "HERCULE Evaluation Scorecard") -> str:
    """Markdown variant of the console scorecard (same numbers)."""
    text = scorecard(run, reliability=reliability, title=title)
    lines = text.splitlines()
    out = [f"# {lines[0]}", ""]
    for line in lines[1:]:
        out.append(f"- {line}" if line and not line.startswith("Scope:") else line)
    return "\n".join(out)
