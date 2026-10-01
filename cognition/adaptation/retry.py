from __future__ import annotations
"""Bounded retry policy (6U §9): every retry has a reason, a budget, and a gate.

Respects max_retries, max_time, PolicyManager verdicts, and autonomy
levels. Identical repeats are refused unless genuinely new evidence
arrived. Escalation to a riskier action requires approval and is
otherwise reported BLOCKED — a failure is never treated as
authorization for a more dangerous attempt.
"""

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

RISK_ORDER = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _risk_level(risk: str) -> int:
    try:
        return RISK_ORDER.index(str(risk or "LOW").upper())
    except ValueError:
        return 0


@dataclass
class RetryBudget:
    max_retries: int = 3
    max_seconds: float = 300.0
    used: int = 0
    started: float = field(default_factory=time.perf_counter)
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def exhausted(self) -> bool:
        if self.used >= max(0, self.max_retries):
            return True
        return (time.perf_counter() - self.started) > max(0.0, self.max_seconds)


def action_signature(action: Dict[str, Any]) -> str:
    import json

    core = {k: action.get(k) for k in ("tool", "action", "input")}
    return json.dumps(core, sort_keys=True, default=str)


def decide_retry(failed_action: Dict[str, Any],
                 revised_action: Dict[str, Any],
                 budget: RetryBudget,
                 policy=None,
                 autonomy: str = "standard",
                 approver: Optional[Callable[[Dict[str, Any]], bool]] = None,
                 new_evidence: bool = False) -> Dict[str, Any]:
    """Gate one retry. Returns {allow, reason, ...} (never raises for policy)."""
    if budget.exhausted:
        return {"allow": False, "reason": "budget exhausted",
                "used": budget.used}
    if action_signature(revised_action) == action_signature(failed_action) \
            and not new_evidence:
        return {"allow": False, "reason": "identical repeat without new evidence",
                "used": budget.used}
    if policy is not None:
        verdict = policy.evaluate(str(revised_action.get("tool", "UNKNOWN")),
                                  {"risk": revised_action.get("risk", "LOW")})
        if not verdict.get("allowed"):
            return {"allow": False, "reason": f"policy denied: {verdict.get('reason')}",
                    "used": budget.used}
        old_risk = _risk_level(failed_action.get("risk", "LOW"))
        new_risk = _risk_level(verdict.get("risk", "LOW"))
        if new_risk > old_risk:
            if approver is None or not approver(verdict):
                return {"allow": False, "reason": "escalation needs approval (BLOCKED)",
                        "used": budget.used, "verdict": verdict}
    if autonomy.strip().lower() in ("manual", "supervised") and budget.used >= 1:
        return {"allow": False, "reason": "autonomy level requires human review",
                "used": budget.used}
    budget.used += 1
    budget.reasons.append(str(revised_action.get("revision_note", "retry")))
    return {"allow": True, "reason": "retry granted", "used": budget.used}
