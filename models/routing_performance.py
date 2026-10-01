from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Routing Performance Memory
Author: Heeran Paul
License: MIT
--------------------------------------------

Aggregate per-model, per-task-type performance: success rate,
latency (exponential moving average), failure rate. A Bayesian-ish
prior (prior_successes/prior_total) means one anomalous result can
never permanently distort routing — ``min_samples`` observations are
needed before history outweighs the prior.

Ownership: MODELS. Read-only input to routing scores.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelPerformance:
    model_name: str
    task_type: str
    samples: int = 0
    successes: int = 0
    failures: int = 0
    latency_ewma_ms: float = 0.0

    def success_rate(self, prior_successes: float = 2.0, prior_total: float = 4.0) -> float:
        total = self.samples + prior_total
        return (self.successes + prior_successes) / total if total else 0.5

    def failure_rate(self) -> float:
        return (self.failures / self.samples) if self.samples else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "task_type": self.task_type,
            "samples": self.samples,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate(), 3),
            "failure_rate": round(self.failure_rate(), 3),
            "latency_ewma_ms": round(self.latency_ewma_ms, 3),
        }


class RoutingMemory:
    """Aggregate routing outcomes with EWMA latency and prior smoothing."""

    def __init__(self, ewma_alpha: float = 0.3, prior_successes: float = 2.0, prior_total: float = 4.0):
        self.ewma_alpha = ewma_alpha
        self.prior_successes = prior_successes
        self.prior_total = prior_total
        self._stats: Dict[str, ModelPerformance] = {}

    @staticmethod
    def _key(model_name: str, task_type: str) -> str:
        return f"{model_name}::{task_type or 'general'}"

    def record(self, model_name: str, task_type: str, success: bool, latency_ms: float = 0.0) -> ModelPerformance:
        key = self._key(model_name, task_type)
        perf = self._stats.get(key)
        if perf is None:
            perf = ModelPerformance(model_name=model_name, task_type=task_type or "general")
            self._stats[key] = perf
        perf.samples += 1
        if success:
            perf.successes += 1
        else:
            perf.failures += 1
        latency_ms = max(0.0, float(latency_ms or 0.0))
        if perf.latency_ewma_ms <= 0:
            perf.latency_ewma_ms = latency_ms
        else:
            perf.latency_ewma_ms = self.ewma_alpha * latency_ms + (1.0 - self.ewma_alpha) * perf.latency_ewma_ms
        return perf

    def stats_for(self, model_name: str, task_type: str) -> ModelPerformance:
        perf = self._stats.get(self._key(model_name, task_type))
        if perf is None:
            return ModelPerformance(model_name=model_name, task_type=task_type or "general")
        return perf

    def success_rate(self, model_name: str, task_type: str) -> float:
        return self.stats_for(model_name, task_type).success_rate(self.prior_successes, self.prior_total)

    def summary(self) -> List[Dict[str, Any]]:
        return [perf.as_dict() for perf in self._stats.values()]

    def best_model(self, candidates: List[str], task_type: str, min_samples: int = 3) -> Optional[str]:
        """Best candidate by smoothed success rate; None until data is mature."""
        mature = [c for c in candidates if self.stats_for(c, task_type).samples >= min_samples]
        if not mature:
            return None
        return max(mature, key=lambda c: self.success_rate(c, task_type))
