from __future__ import annotations
"""
Minimal public contract for the Phase 5 decision-intelligence candidate
validation gate. The decision engine only considers candidates that pass
this gate; invalid candidates are discarded BEFORE scoring (never
executed, never bypassed).
"""

from typing import Any, Dict, List, Optional, Sequence

from cognition.capabilities.capability import Capability, coerce_capability


VALID_RISKS = ("LOW", "MEDIUM", "HIGH")


def normalize_risk(value: str) -> str:
    r = str(value or "LOW").upper()
    return r if r in VALID_RISKS else "MEDIUM"


def validate_candidate(
    candidate: Dict[str, Any],
    *,
    known_capabilities: Optional[Sequence[str]] = None,
    known_abilities: Optional[Sequence[str]] = None,
    environment: str = "default",
) -> Dict[str, Any]:
    """Validate one strategy candidate at the decision-intelligence boundary.

    Returns {"ok": bool, "problems": [...], "candidate_id": ...}.

    This is a DECISION-ENGINE gate, not a full plan validator. Full plan
    validation (registry/policy/verification) still runs downstream and
    remains authoritative. This gate's job is to reject obviously malformed
    model proposals BEFORE they reach scoring, and to give honest reasons.
    """
    data = dict(candidate or {})
    problems: List[Dict[str, Any]] = []
    cid = str(data.get("strategy_id", data.get("id", "")) or "candidate")
    goal = str(data.get("goal", "") or "").strip()
    if not goal:
        problems.append({"code": "MISSING_GOAL", "detail": "strategy goal must be non-empty"})
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append({"code": "EMPTY_STEPS", "detail": "strategy must have at least one step"})
    else:
        for i, step in enumerate(steps):
            sdict = dict(step or {})
            sid = str(sdict.get("step_id", sdict.get("id", f"step-{i+1}"))) or f"step-{i+1}"
            sg = str(sdict.get("goal", sdict.get("description", sdict.get("objective", ""))) or "").strip()
            if not sg:
                problems.append({"code": "MISSING_STEP_GOAL", "step": sid, "detail": "step has no goal/objective"})
            caps = sdict.get("required_capabilities")
            if not caps:
                problems.append({"code": "MISSING_CAPABILITIES", "step": sid, "detail": "step declares no capabilities"})
            else:
                for c in caps:
                    c = str(c)
                    try:
                        coerce_capability(c)
                    except ValueError:
                        problems.append({"code": "UNKNOWN_CAPABILITY", "step": sid, "detail": c})
    # risk sanity
    risk = str(data.get("risk", "LOW")).upper()
    if risk not in VALID_RISKS:
        problems.append({"code": "UNKNOWN_RISK", "detail": risk})
    # ability sanity (registry is authoritative downstream; here only
    # reject obviously unknown names when we actually know the registry)
    if known_abilities:
        for a in (data.get("required_abilities") or []):
            if str(a).upper() not in {str(x).upper() for x in known_abilities}:
                problems.append({"code": "UNKNOWN_ABILITY", "detail": str(a)})
    if known_capabilities:
        for c in (data.get("required_capabilities") or []):
            if str(c).upper() not in {str(x).upper() for x in known_capabilities}:
                problems.append({"code": "UNKNOWN_CAPABILITY", "detail": str(c)})
    ok = not problems
    return {"ok": ok, "problems": problems, "candidate_id": cid}
