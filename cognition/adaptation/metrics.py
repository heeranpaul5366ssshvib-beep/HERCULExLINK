from __future__ import annotations
"""Learning-efficiency metrics (6U §13), per task family.

- Mistake Recovery Rate = corrected tasks / tasks needing correction
- Learning Efficiency = performance_after / performance_before
- Repeated Failure Rate = repeated same failure / total failures
Plus first-attempt success, retries, tool calls, time/tokens.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class FamilyStats:
    tasks: int = 0
    first_attempt_ok: int = 0
    needed_correction: int = 0
    corrected: int = 0
    failures: int = 0
    repeated_same: int = 0
    retries: int = 0
    tool_calls: int = 0
    wall_s: float = 0.0
    score_before: float = 0.0
    score_after: float = 0.0
    _last_sigs: List[str] = field(default_factory=list)

    def record(self, trace: Dict[str, Any]) -> None:
        attempts = trace.get("attempts", [])
        self.tasks += 1
        self.retries += int(trace.get("retries", 0))
        self.wall_s += float(trace.get("wall_s", 0.0))
        sigs = [a.get("action", "") for a in attempts]
        for sig in sigs[1:]:
            if sig in sigs[:sigs.index(sig)] or sig in self._last_sigs[-8:]:
                self.repeated_same += 1
        self._last_sigs.extend(sigs)
        self._last_sigs = self._last_sigs[-32:]
        self.failures += max(0, len(attempts) - (1 if trace.get("verified") else 0))
        if trace.get("verified") and not trace.get("recovered"):
            self.first_attempt_ok += 1
        if trace.get("retries", 0) > 0 or len(attempts) > 1:
            self.needed_correction += 1
            if trace.get("verified"):
                self.corrected += 1

    def summary(self) -> Dict[str, Any]:
        t = max(1, self.tasks)
        nc = max(1, self.needed_correction)
        return {
            "tasks": self.tasks,
            "first_attempt_success_rate": round(self.first_attempt_ok / t, 3),
            "mistake_recovery_rate": round(self.corrected / nc, 3),
            "repeated_failure_rate": round(self.repeated_same / max(1, self.failures), 3),
            "learning_efficiency": round(self.score_after / max(1e-9, self.score_before), 3)
            if self.score_before > 0 else None,
            "mean_retries": round(self.retries / t, 2),
            "mean_wall_s": round(self.wall_s / t, 2),
        }


class LearningMetrics:
    """Registry of per-family stats."""

    def __init__(self):
        self._families: Dict[str, FamilyStats] = {}

    def record(self, family: str, trace: Dict[str, Any]) -> None:
        self._families.setdefault(family, FamilyStats()).record(trace)

    def set_scores(self, family: str, before: float, after: float) -> None:
        stats = self._families.setdefault(family, FamilyStats())
        stats.score_before, stats.score_after = float(before), float(after)

    def report(self) -> Dict[str, Any]:
        return {fam: stats.summary() for fam, stats in self._families.items()}
