from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Capable Plan Construction
Author: Heeran Paul
License: MIT
--------------------------------------------

Builds enriched plan steps on top of the authoritative Planner: each
step carries required capabilities (inferred deterministically),
default verification criteria per capability, risk, timeouts and retry
policy. The legacy ``create_plan`` shape is untouched.
"""

import re
from typing import Any, Dict, List, Optional

from cognition.capabilities.capability import CAPABILITY_RISK, Capability, RiskLevel, coerce_capability
from cognition.capabilities.effects import default_effect_for
from cognition.capabilities.inference import infer_capabilities

# Deterministic multi-action splitter: explicit sequencing language only.
# Matched spans are removed; the surviving fragments become ordered steps
# with chained dependencies. Anything without such language stays one step.
_SPLIT_RE = re.compile(
    r"\s*(?:then|and then|next|after that|followed by)\s+|\s*;\s*|\s*\n+\s*",
    re.IGNORECASE,
)


def decompose_goal(goal: str) -> List[str]:
    """Split a multi-action goal into ordered step descriptions.

    Deterministic and conservative: only explicit sequencing ("then",
    "and then", ";", newlines, "next", "after that") splits. Fragments
    keep document order; callers chain them via dependencies.
    """
    text = str(goal or "").strip().rstrip(".")
    if not text:
        return [str(goal)]
    parts = [p.strip().rstrip(".") for p in _SPLIT_RE.split(text)]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return [text]
    return parts

# Default verification criteria per capability: WHAT must hold, not how.
VERIFICATION_DEFAULTS: Dict[Capability, List[str]] = {
    Capability.FILE_READ: ["content returned and non-empty"],
    Capability.FILE_WRITE: ["target exists", "content matches expected state"],
    Capability.DOCUMENT_READ: ["summary cites source sections"],
    Capability.DOCUMENT_WRITE: ["document exists with expected sections"],
    Capability.CODE_EDIT: ["diff applies", "no syntax errors"],
    Capability.CODE_EXECUTION: ["exit status 0", "expected outputs present"],
    Capability.TERMINAL_EXECUTE: ["exit status 0", "relevant outputs captured"],
    Capability.WEB_SEARCH: ["evidence set non-empty with sources"],
    Capability.KNOWLEDGE_RETRIEVAL: ["results cite provenance"],
    Capability.BROWSER_USE: ["target page reached"],
    Capability.DATABASE_READ: ["rows returned match query"],
    Capability.DATABASE_WRITE: ["write acknowledged", "read-back matches"],
    Capability.MATH: ["result verified by recomputation"],
    Capability.SYSTEM_OBSERVE: ["health payload recorded"],
    Capability.APPLICATION_CONTROL: ["service reached expected state"],
    Capability.VISION_ANALYSIS: ["findings reference image regions"],
    Capability.SPEECH_RECOGNITION: ["transcript non-empty"],
    Capability.TEXT_TO_SPEECH: ["audio artifact produced"],
}

DEFAULT_TIMEOUT_S = 120
DEFAULT_RETRIES = 1


def build_capable_step(
    step_id: str,
    description: str,
    objective: str = "",
    dependencies: Optional[List[str]] = None,
    required_inputs: Optional[List[str]] = None,
    expected_outputs: Optional[List[str]] = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    max_retries: int = DEFAULT_RETRIES,
    effect: Optional[str] = None,
    state_check: Optional[Dict[str, Any]] = None,
    compensation: Optional[Dict[str, Any]] = None,
    resume_policy: Optional[str] = None,
    capabilities: Optional[List[str]] = None,
    explicit_capabilities: Optional[List[str]] = None,
    semantic_report: Optional[Dict[str, Any]] = None,
    required_ability: str = "",
    inputs: Optional[Dict[str, Any]] = None,
    expected_output: str = "",
) -> Dict[str, Any]:
    if capabilities is None:
        capabilities = [c.value for c in infer_capabilities(description)]
    else:
        capabilities = [str(c).upper() for c in capabilities]
    enums = []
    for name in capabilities:
        try:
            enums.append(coerce_capability(name))
        except ValueError:
            enums.append(None)  # unknown: generic criteria, medium risk
    risks = [CAPABILITY_RISK.get(c, RiskLevel.MEDIUM) if c is not None else RiskLevel.MEDIUM for c in enums]
    order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]
    risk = max(risks, key=lambda r: order.index(r)) if risks else RiskLevel.LOW
    criteria: List[str] = []
    for name, cap in zip(capabilities, enums):
        criteria.extend(VERIFICATION_DEFAULTS.get(cap, ["tool reported success"]) if cap is not None else ["tool reported success"])
    known_enums = [c for c in enums if c is not None]
    effect_class = effect or (default_effect_for(known_enums).value if known_enums else "EFFECTFUL")
    return {
        "step_id": step_id,
        "description": description,
        "objective": objective or description,
        "goal": objective or description,
        "dependencies": list(dependencies or []),
        "required_capabilities": list(capabilities),
        "required_ability": str(required_ability or ""),
        "inputs": dict(inputs or {}),
        "expected_output": str(expected_output or ""),
        "preferred_tools": [],
        "acceptable_tools": [],
        "required_inputs": list(required_inputs or []),
        "expected_outputs": list(expected_outputs or []),
        "expected_state": "",
        "verification_criteria": criteria,
        "risk": risk.value,
        "permissions_required": list(capabilities),
        "execution_constraints": {},
        "timeout_s": timeout_s,
        "retry_policy": {"max_retries": max_retries, "retry_destructive": False},
        "effect": effect_class,
        "state_check": dict(state_check or {}),
        "compensation": dict(compensation) if compensation else None,
        "resume_policy": resume_policy or "default",
        "explicit_capabilities": [str(c).upper() for c in (explicit_capabilities or [])],
        "semantic_report": dict(semantic_report or {}),
        "status": "pending",
    }


def build_capable_plan(goal: str, steps: List[Any], resolver=None,
                       chain: bool = False) -> List[Dict[str, Any]]:
    """Enrich planner step descriptions into capable steps (multi-tool
    steps keep every inferred capability; decomposition happens later).
    Mapping steps may already carry effect/state_check/compensation/
    resume_policy/expected_outputs/timeout/retries/explicit_capabilities,
    which are honored. With ``chain=True`` (decomposed sequential goals),
    step N depends on step N-1 so the loop never runs a dependent step
    before its prerequisite is verified.

    When ``resolver`` (hybrid.resolve_capabilities-compatible callable)
    is given, each step's required capabilities come from the validated
    hybrid resolution; otherwise the legacy deterministic inference
    runs byte-identically.
    """
    capable = []
    for i, step in enumerate(steps):
        if isinstance(step, str):
            description, deps, extra = step, [], {}
        else:
            description = str(step.get("description", step))
            deps = list(step.get("dependencies", []))
            extra = step
        resolution = None
        capabilities = None
        if resolver is not None:
            try:
                resolution = resolver(description, extra)
                capabilities = list(resolution.get("final", []))
            except Exception:
                resolution, capabilities = None, None
        if capabilities is None and isinstance(extra.get("required_capabilities"), list):
            # Dict steps (e.g. cognitive proposals) may declare validated
            # capabilities; unknown names still fail downstream validation.
            capabilities = list(extra.get("required_capabilities") or [])
        built = build_capable_step(
            f"step-{i + 1}", description, objective=str(goal), dependencies=deps,
            required_inputs=extra.get("required_inputs"),
            expected_outputs=extra.get("expected_outputs"),
            timeout_s=int(extra.get("timeout_s", DEFAULT_TIMEOUT_S)),
            max_retries=int(extra.get("max_retries", DEFAULT_RETRIES)),
            effect=extra.get("effect"),
            state_check=extra.get("state_check"),
            compensation=extra.get("compensation"),
            resume_policy=extra.get("resume_policy"),
            capabilities=capabilities,
            explicit_capabilities=extra.get("explicit_capabilities"),
            semantic_report=(resolution or {}).get("report"),
            required_ability=str(extra.get("required_ability", "") or ""),
            inputs=extra.get("inputs") if isinstance(extra.get("inputs"), dict) else None,
            expected_output=str(extra.get("expected_output", "") or ""),
        )
        if extra.get("step_id"):
            built["step_id"] = str(extra["step_id"])
        # Preserve caller-supplied verification criteria (e.g. the model's
        # own verification text); deterministic criteria always remain.
        for criterion in extra.get("verification_criteria", []) or []:
            text = str(criterion or "").strip()
            if text and text not in built["verification_criteria"]:
                built["verification_criteria"] = [text] + built["verification_criteria"]
        if resolution is not None:
            built["optional_capabilities"] = list(resolution.get("optional", []))
        if chain and capable:
            prev = capable[-1].get("step_id", "")
            if prev and prev not in built["dependencies"]:
                built["dependencies"].append(prev)
        capable.append(built)
    return capable
