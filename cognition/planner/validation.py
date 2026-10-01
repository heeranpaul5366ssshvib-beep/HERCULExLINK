from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Plan Validation
Author: Heeran Paul
License: MIT
--------------------------------------------

Pre-execution plan gate: every step needs capabilities, every
capability needs an available provider, dependencies must be
acyclic, permissions pre-checked, verification present. Invalid
plans are rejected BEFORE execution — including on replan.
"""

from typing import Any, Dict, List, Optional, Set

from cognition.capabilities.capability import coerce_capability


def _step_id(step: Dict[str, Any], index: int) -> str:
    return str(step.get("step_id", f"step-{index + 1}"))


VALID_RISKS = ("LOW", "MEDIUM", "HIGH")


def validate_plan(
    steps: List[Dict[str, Any]],
    capability_registry=None,
    policy_manager=None,
    environment: str = "default",
    ability_manager=None,
    agent_manager=None,
    goal: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a capable plan. Returns a structured report."""
    step_reports: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    if goal is not None and not str(goal).strip():
        problems.append({"code": "INVALID_GOAL", "detail": "plan goal must be a non-empty string"})
    ids = [_step_id(s, i) for i, s in enumerate(steps)]
    if len(set(ids)) != len(ids):
        problems.append({"code": "DUPLICATE_STEP_ID", "detail": "step ids must be unique"})

    # Dependency graph checks.
    known = set(ids)
    for i, step in enumerate(steps):
        for dep in step.get("dependencies", []) or []:
            if dep not in known:
                problems.append({"code": "UNKNOWN_DEPENDENCY", "step": ids[i], "detail": dep})
    # Cycle detection (DFS).
    edges = {sid: [d for d in (s.get("dependencies", []) or []) if d in known] for sid, s in zip(ids, steps)}
    visiting: Set[str] = set()
    done: Set[str] = set()
    cyclic: Set[str] = set()

    def visit(node: str, stack: List[str]):
        if node in done:
            return
        if node in visiting:
            cyclic.update(stack[stack.index(node):])
            return
        visiting.add(node)
        for dep in edges.get(node, []):
            visit(dep, stack + [dep])
        visiting.discard(node)
        done.add(node)

    for sid in ids:
        visit(sid, [sid])
    if cyclic:
        problems.append({"code": "CIRCULAR_DEPENDENCY", "detail": sorted(cyclic)})

    for i, step in enumerate(steps):
        sid = ids[i]
        caps: List[str] = []
        try:
            caps = [coerce_capability(c).value for c in (step.get("required_capabilities", []) or [])]
        except ValueError as exc:
            problems.append({"code": "UNKNOWN_CAPABILITY", "step": sid, "detail": str(exc)})
        coverage = "FULL"
        missing: List[str] = []
        unavailable: List[str] = []
        permission_conflicts: List[str] = []
        if not caps:
            coverage = "NONE"
            problems.append({"code": "MISSING_CAPABILITIES", "step": sid, "detail": "no required capabilities"})
        elif capability_registry is not None:
            for cap in caps:
                providers = capability_registry.providers_for(cap, environment)
                if not providers:
                    missing.append(cap)
                    continue
                live = [p for p in providers
                        if str(capability_registry.provider_health(p, ability_manager, agent_manager).get("state", "")).upper()
                        in ("READY", "DEGRADED")]
                if not live:
                    unavailable.append(cap)
            if missing or unavailable:
                coverage = "NO_COVERAGE"
            # PARTIAL vs FULL is decided at tool-match time (multi-tool
            # steps may still reach FULL via several providers).
        if not step.get("verification_criteria"):
            problems.append({"code": "MISSING_VERIFICATION", "step": sid, "detail": "no verification criteria"})
        # Required structural fields (Stage 8 plan contract).
        if not str(step.get("goal", step.get("objective", step.get("description", ""))) or "").strip():
            problems.append({"code": "MISSING_FIELD", "step": sid, "detail": "no goal/objective/description"})
        risk = str(step.get("risk", "LOW") or "LOW").upper()
        if risk not in VALID_RISKS:
            problems.append({"code": "INVALID_RISK", "step": sid, "detail": f"risk must be one of {VALID_RISKS}"})
        inputs = step.get("inputs", {})
        if inputs is not None and not isinstance(inputs, dict):
            problems.append({"code": "INVALID_INPUTS", "step": sid, "detail": "inputs must be an object"})
        # A named ability must actually exist — the model may suggest,
        # only the registry may confirm.
        required_ability = str(step.get("required_ability", "") or "").strip()
        if required_ability and ability_manager is not None:
            try:
                exists = ability_manager.exists(required_ability)
            except Exception:
                try:
                    exists = ability_manager.get(required_ability) is not None
                except Exception:
                    exists = False
            if not exists:
                problems.append({"code": "UNKNOWN_ABILITY", "step": sid,
                                 "detail": f"no such ability: {required_ability}"})
        if policy_manager is not None:
            for cap in caps:
                try:
                    decision = policy_manager.evaluate(cap, {"risk": "LOW"}, actor="plan-validator")
                    if not decision.get("allowed", True):
                        permission_conflicts.append(cap)
                except Exception as exc:
                    problems.append({"code": "POLICY_ERROR", "step": sid, "detail": str(exc)[:160]})
            if permission_conflicts:
                problems.append({"code": "PERMISSION_CONFLICT", "step": sid, "detail": permission_conflicts})
        step_reports.append({"step_id": sid, "capabilities": caps, "coverage": coverage,
                             "missing": missing, "unavailable": unavailable,
                             "permission_conflicts": permission_conflicts})

    # Plan quality metrics (§17 + Phase M semantic extension).
    semantic_confidences: List[float] = []
    semantic_rejected = 0
    semantic_fallbacks = 0
    for s in steps:
        report = s.get("semantic_report") or {}
        if not report:
            continue
        for entry in report.get("accepted", []):
            if isinstance(entry.get("confidence"), (int, float)):
                semantic_confidences.append(float(entry["confidence"]))
        semantic_rejected += len(report.get("rejected", []))
        if report.get("fallback_used"):
            semantic_fallbacks += 1
    metrics = {
        "missing_capabilities": sum(len(r["missing"]) for r in step_reports),
        "unavailable_capabilities": sum(len(r["unavailable"]) for r in step_reports),
        "steps_without_capabilities": sum(1 for r in step_reports if not r["capabilities"]),
        "steps_without_verification": sum(1 for s in steps if not s.get("verification_criteria")),
        "unresolved_dependencies": sum(1 for p in problems if p["code"] == "UNKNOWN_DEPENDENCY"),
        "permission_conflicts": sum(1 for p in problems if p["code"] == "PERMISSION_CONFLICT"),
        "redundant_steps": _redundant_steps(steps),
        "semantic_confidence": round(sum(semantic_confidences) / len(semantic_confidences), 3) if semantic_confidences else None,
        "semantic_rejected": semantic_rejected,
        "semantic_fallbacks": semantic_fallbacks,
    }
    valid = not problems
    return {"valid": valid, "steps": step_reports, "problems": problems, "metrics": metrics}


def _redundant_steps(steps: List[Dict[str, Any]]) -> int:
    seen = set()
    redundant = 0
    for step in steps:
        key = str(step.get("description", "")).strip().lower()
        if key in seen:
            redundant += 1
        seen.add(key)
    return redundant


def coverage_summary(report: Dict[str, Any]) -> Dict[str, int]:
    summary = {"FULL": 0, "PARTIAL": 0, "NO_COVERAGE": 0, "NONE": 0}
    for step in report.get("steps", []):
        summary[step.get("coverage", "NONE")] = summary.get(step.get("coverage", "NONE"), 0) + 1
    return summary
