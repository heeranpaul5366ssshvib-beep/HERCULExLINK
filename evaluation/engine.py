from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Engine 2.0
Author: Heeran Paul
License: MIT
--------------------------------------------

One evaluation entry point for MODEL / MEMORY / RETRIEVAL / CONTEXT /
REASONING / PLANNING / TOOLS / AGENTS / TASKS. Each evaluation keeps
input, expected, observed, metrics, pass/fail and diagnostics, and
every run is retained for trend/regression comparison.

Also hosts the performance baseline: timed measurements for context
creation, retrieval, model routing, task planning, tool dispatch and
end-to-end completion, recorded before optimization.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from evaluation.metrics import SubsystemScore, aggregate_scores

Scorer = Callable[[Dict[str, Any]], SubsystemScore]


@dataclass
class Evaluation:
    name: str
    subsystem: str
    passed: bool
    score: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    expected: Any = None
    observed: Any = None
    diagnostics: str = ""
    evaluated_at: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "subsystem": self.subsystem,
            "passed": self.passed,
            "score": round(float(self.score), 3),
            "metrics": dict(self.metrics),
            "expected": self.expected,
            "observed": self.observed,
            "diagnostics": self.diagnostics,
            "evaluated_at": self.evaluated_at,
        }


class EvaluationEngine:
    """Registry of per-subsystem scorers plus run history."""

    def __init__(self):
        self._scorers: Dict[str, Scorer] = {}
        self.runs: List[Evaluation] = []

    def register(self, subsystem: str, scorer: Scorer) -> None:
        self._scorers[subsystem] = scorer

    def subsystems(self) -> List[str]:
        return sorted(self._scorers)

    def evaluate(self, subsystem: str, payload: Optional[Dict[str, Any]] = None) -> Evaluation:
        scorer = self._scorers.get(subsystem)
        if scorer is None:
            raise KeyError(f"no scorer registered for subsystem: {subsystem}")
        result = scorer(dict(payload or {}))
        evaluation = Evaluation(
            name=f"{subsystem}-eval-{len(self.runs) + 1}",
            subsystem=subsystem,
            passed=bool(result.passed),
            score=float(result.score),
            metrics=dict(result.metrics),
            observed=result.metrics.get("observed"),
            expected=result.metrics.get("expected"),
            diagnostics=result.detail,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.runs.append(evaluation)
        return evaluation

    def evaluate_all(self, payloads: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        payloads = payloads or {}
        scores = [self.evaluate(name, payloads.get(name)) for name in self.subsystems()]
        outcome = aggregate_scores(
            [SubsystemScore(s.subsystem, s.score, s.passed, s.metrics, s.diagnostics) for s in scores]
        )
        outcome["evaluations"] = [s for s in scores]
        return outcome

    def export(self, path: Union[str, Path]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps([r.as_dict() for r in self.runs], indent=2), encoding="utf-8")
        return target


@dataclass
class PerformanceBaseline:
    """Timed baseline for one pipeline stage."""

    stage: str
    latency_ms: float
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"stage": self.stage, "latency_ms": round(self.latency_ms, 3), "detail": dict(self.detail)}


def measure_stage(stage: str, fn: Callable[[], Any]) -> PerformanceBaseline:
    """Time one callable; exceptions propagate (never faked)."""
    started = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    detail = result if isinstance(result, dict) else {"result": str(result)[:200]}
    return PerformanceBaseline(stage=stage, latency_ms=elapsed_ms, detail=detail)


def build_baseline(stages: Dict[str, Callable[[], Any]]) -> Dict[str, Any]:
    """Run the standard baseline suite and return a storable report."""
    measurements = [measure_stage(name, fn) for name, fn in stages.items()]
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "stages": [m.as_dict() for m in measurements],
        "total_ms": round(sum(m.latency_ms for m in measurements), 3),
    }
