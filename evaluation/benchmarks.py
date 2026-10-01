from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Benchmark Registry
Author: Heeran Paul
License: MIT
--------------------------------------------

Deterministic benchmark categories with runnable fixture cases:

REASONING / PLANNING / TOOL_SELECTION / MEMORY_RETRIEVAL /
KNOWLEDGE_RETRIEVAL / MODEL_ROUTING / TASK_COMPLETION / FAILURE_RECOVERY /
SEMANTIC_CAPABILITY_INFERENCE

Cases are pure and hermetic (no live models, no network): retrieval
benchmarks run against an in-memory ingested fixture, routing
benchmarks against mock adapters. Results persist in-memory and can
be exported to JSON for regression tracking.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


class BenchmarkCategory(str, Enum):
    REASONING = "reasoning"
    PLANNING = "planning"
    TOOL_SELECTION = "tool_selection"
    MEMORY_RETRIEVAL = "memory_retrieval"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    MODEL_ROUTING = "model_routing"
    TASK_COMPLETION = "task_completion"
    FAILURE_RECOVERY = "failure_recovery"
    SEMANTIC_CAPABILITY_INFERENCE = "semantic_capability_inference"


@dataclass
class BenchmarkCase:
    name: str
    category: BenchmarkCategory
    run: Callable[[], Dict[str, Any]]
    description: str = ""

    def execute(self) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            metrics = dict(self.run() or {})
            passed = bool(metrics.get("passed", True))
            error = ""
        except Exception as exc:
            metrics, passed, error = {}, False, str(exc)
        return {
            "name": self.name,
            "category": self.category.value,
            "passed": passed,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 3),
            "metrics": metrics,
            "error": error,
        }


class BenchmarkRegistry:
    """Category-organized benchmark cases with run history."""

    def __init__(self):
        self._cases: Dict[str, BenchmarkCase] = {}
        self.history: List[Dict[str, Any]] = []

    def register(self, case: BenchmarkCase) -> None:
        self._cases[case.name] = case

    def cases(self, category: Optional[BenchmarkCategory] = None) -> List[BenchmarkCase]:
        items = list(self._cases.values())
        if category is not None:
            items = [c for c in items if c.category == category]
        return items

    def run_case(self, name: str) -> Dict[str, Any]:
        case = self._cases.get(name)
        if case is None:
            raise KeyError(f"unknown benchmark case: {name}")
        result = case.execute()
        self.history.append(result)
        return result

    def run_category(self, category: BenchmarkCategory) -> Dict[str, Any]:
        results = [c.execute() for c in self.cases(category)]
        self.history.extend(results)
        return self._summarize(category.value, results)

    def run_all(self) -> Dict[str, Any]:
        results = [c.execute() for c in self.cases()]
        self.history.extend(results)
        return self._summarize("all", results)

    @staticmethod
    def _summarize(label: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        passed = sum(1 for r in results if r["passed"])
        return {
            "scope": label,
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "pass_rate": round(passed / len(results), 3) if results else 0.0,
            "results": results,
        }

    def export(self, path: Union[str, Path]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.history, indent=2), encoding="utf-8")
        return target
