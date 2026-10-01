from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Quality & Subsystem Metrics
Author: Heeran Paul
License: MIT
--------------------------------------------

Task quality is never one arbitrary number: ``TaskQuality`` keeps the
underlying metrics (completion, verification, error rate, efficiency,
feedback) alongside the weighted score. ``compute_task_quality``
distills a durable TaskManager task dict without touching the task
lifecycle.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_WEIGHTS = {
    "completion": 0.30,
    "verification": 0.30,
    "error_rate": 0.15,
    "efficiency": 0.15,
    "feedback": 0.10,
}


@dataclass
class TaskQuality:
    completion: float = 0.0
    verification: float = 0.0
    error_rate: float = 0.0  # 0 = no errors, 1 = all errors
    efficiency: float = 0.0
    feedback: float = 0.5  # neutral when no user feedback exists

    @property
    def score(self) -> float:
        return round(
            _WEIGHTS["completion"] * self.completion
            + _WEIGHTS["verification"] * self.verification
            + _WEIGHTS["error_rate"] * (1.0 - self.error_rate)
            + _WEIGHTS["efficiency"] * self.efficiency
            + _WEIGHTS["feedback"] * self.feedback,
            3,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "completion": self.completion,
            "verification": self.verification,
            "error_rate": self.error_rate,
            "efficiency": self.efficiency,
            "feedback": self.feedback,
            "score": self.score,
        }


def compute_task_quality(
    task: Dict[str, Any],
    max_retries: int = 2,
    feedback: Optional[float] = None,
) -> TaskQuality:
    """Score a TaskManager task dict on the five quality dimensions."""
    status = str(task.get("status", "")).upper()
    completion = 1.0 if status == "COMPLETED" else (0.5 if status in ("VERIFYING", "RETRYING", "RECOVERING") else 0.0)
    verification_state = str(task.get("verification_state", "")).upper()
    verification_payload = task.get("verification") or {}
    if verification_state == "VERIFIED" or verification_payload.get("verified"):
        verification = 1.0
    elif verification_state == "RUNNING" or status == "VERIFYING":
        verification = 0.5
    else:
        verification = 0.0
    errors = list(task.get("errors") or [])
    attempts = max(1, int(task.get("retry_count", 0) or 0) + 1)
    error_rate = round(min(1.0, len(errors) / attempts), 3)
    retries = int(task.get("retry_count", 0) or 0)
    efficiency = round(max(0.0, 1.0 - retries / max(1, max_retries + 1)), 3)
    return TaskQuality(
        completion=completion,
        verification=verification,
        error_rate=error_rate,
        efficiency=efficiency,
        feedback=float(feedback) if feedback is not None else 0.5,
    )


@dataclass
class SubsystemScore:
    """One subsystem evaluation: score plus retained raw metrics."""

    name: str
    score: float
    passed: bool
    metrics: Dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": round(float(self.score), 3),
            "passed": bool(self.passed),
            "metrics": dict(self.metrics),
            "detail": self.detail,
        }


def aggregate_scores(scores: List[SubsystemScore]) -> Dict[str, Any]:
    """Mean aggregate that never hides the per-subsystem breakdown."""
    if not scores:
        return {"score": 0.0, "passed": False, "subsystems": []}
    mean = sum(s.score for s in scores) / len(scores)
    return {
        "score": round(mean, 3),
        "passed": all(s.passed for s in scores),
        "subsystems": [s.as_dict() for s in scores],
    }
