from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Cognitive Planner
Author: Heeran Paul
License: MIT
--------------------------------------------

LLM-assisted multi-step planning under deterministic authority.

The model may PROPOSE a structured plan (goal + steps with
dependencies, capabilities, optional ability hints, inputs, expected
outputs, verification text, risk). The deterministic pipeline then
DECIDES: structure validation (models.structured) → conversion to
capable steps → plan validation (registry/policy/verification) →
DecisionEngine selection. Invalid proposals fall back to the
deterministic planner honestly — never to execution.

Separation is strict (Stage 8 Phase 9):

Reasoner         → analyzes the problem (existing LLM reasoning call)
CognitivePlanner → proposes one structured candidate plan (one LLM call)
DecisionEngine   → selects between validated candidates (deterministic)
Planner          → the single authoritative plan constructor
AutonomousLoop   → the sole execution mechanism
"""

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from cognition.capabilities.inference import infer_capabilities

# Planning policy (Phase 3): when the goal shows genuine multi-intent,
# escalate to the model. Single-capability/single-clause goals stay on
# the free deterministic path. Override with HERCULE_COGNITIVE_PLANNING
# = always|never|auto (default auto).
COGNITIVE_PLANNING_ENV = "HERCULE_COGNITIVE_PLANNING"
CLAUSE_SPLIT_RE = re.compile(r"[,;]|\band\b", re.IGNORECASE)


def planning_policy(goal: str) -> Dict[str, Any]:
    """Deterministic planner-mode selection (no model call).

    Returns {"mode": "deterministic"|"cognitive", "reason": ...}.
    """
    from system.config.runtime_config import load_runtime_config
    forced = load_runtime_config().cognitive_planning
    text = str(goal or "")
    caps = {c.value for c in infer_capabilities(text)}
    clauses = [c.strip() for c in CLAUSE_SPLIT_RE.split(text) if c.strip()]
    multi_capability = len(caps) >= 2
    multi_clause = len(clauses) >= 3
    if forced == "always":
        return {"mode": "cognitive", "reason": "operator override (always)"}
    if forced == "never":
        return {"mode": "deterministic", "reason": "operator override (never)"}
    if multi_capability and multi_clause:
        return {"mode": "cognitive",
                "reason": f"multi-intent: {sorted(caps)} across {len(clauses)} clauses"}
    return {"mode": "deterministic",
            "reason": f"simple: {sorted(caps) or ['no-capability']} in {len(clauses)} clause(s)"}


def render_plan_prompt(goal: str, analysis_summary: str, memory_context: str,
                       allowed_capabilities: List[str],
                       allowed_abilities: List[str]) -> str:
    """Bounded plan-proposal prompt (schema + allowlists, no CoT request)."""
    caps = ", ".join(sorted(allowed_capabilities))
    tools = ", ".join(sorted(allowed_abilities)) or "(none registered)"
    short_context = str(memory_context or "")[:300]
    short_analysis = str(analysis_summary or "")[:150]
    context_block = f"\nPast experience (ADVISORY):\n{short_context}\n" if short_context else ""
    return (
        "Propose an EXECUTION PLAN. No execution, no authorization, no policy override. "
        "Rules: ONLY allowed capabilities; ability from registered list or null; "
        "true dependencies via step ids (independent steps: []); at most 8 steps."
        f"\n\nCapabilities: {caps}"
        f"\nAbilities (or null): {tools}"
        f"\n\nGoal:\n{goal}"
        f"\n\nAnalysis:\n{short_analysis}"
        f"{context_block}"
        '\nStart your response with the { character: no preamble, no explanations, '
        'no code fences. Emit compact JSON with minimal whitespace. Only '
        'step_id/goal/dependencies/required_capabilities are required; add '
        'required_ability/inputs/expected_output/verification/risk only when needed: '
        '{"goal": "<restated goal>", "steps": [{'
        '"step_id": "step-1", "goal": "<short objective>", "dependencies": [], '
        '"required_capabilities": ["<ALLOWED>"]}]}'
    )


PROPOSAL_MAX_TOKENS = 160


def propose_plan(model_manager: Any, goal: str, analysis_summary: str,
                 memory_context: str, allowed_capabilities: List[str],
                 allowed_abilities: List[str],
                 timeout_s: Optional[float] = None) -> Tuple[bool, Dict[str, Any], str, Dict[str, Any]]:
    """One bounded model call → validated plan proposal.

    Returns (ok, proposal, error, metrics). ``metrics`` carries model,
    latency, and token counts where the adapter reports them. Any
    failure (unavailable model, timeout, malformed output, unknown
    names) returns ok=False with a structured error — the caller falls
    back to the deterministic planner.
    """
    from models.structured import parse_cognitive_plan

    prompt = render_plan_prompt(goal, analysis_summary, memory_context,
                                allowed_capabilities, allowed_abilities)
    try:
        route = model_manager.route_for_purpose("planning")
        model_name = route[0] if isinstance(route, (list, tuple)) else None
    except Exception:
        model_name = None
    try:
        kwargs: Dict[str, Any] = {"options": {"num_predict": PROPOSAL_MAX_TOKENS}}
        if timeout_s is not None:
            kwargs["timeout_s"] = timeout_s
        if model_name:
            raw = model_manager.generate(prompt, model=model_name, **kwargs)
        else:
            raw = model_manager.generate(prompt, **kwargs)
    except Exception as exc:
        return False, {}, f"model call failed: {exc}", {"model": model_name or ""}
    if isinstance(raw, str) and raw.startswith("[HERCULE Error]"):
        return False, {}, f"model unavailable: {raw[:200]}", {"model": model_name or ""}
    ok, proposal, error = parse_cognitive_plan(raw, tuple(allowed_abilities))
    metrics = {"model": model_name or "", "raw_chars": len(str(raw or ""))}
    import logging as _logging
    from system.config.runtime_config import load_runtime_config
    if load_runtime_config().debug_raw:
        _logging.getLogger("HERCULE.RequestLifecycle").info(
            "PLAN_PROPOSAL raw=[%s]", str(raw or "")[:1500])
    if not ok:
        return False, {}, error, metrics
    return True, proposal, "", metrics


def plan_from_proposal(goal: str, proposal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a validated proposal into capable steps (no model, no I/O)."""
    from cognition.planner.capable import build_capable_step

    steps: List[Dict[str, Any]] = []
    for index, raw in enumerate(proposal.get("steps", []) or []):
        built = build_capable_step(
            str(raw.get("step_id", f"step-{index + 1}")),
            str(raw.get("goal", "")),
            objective=str(goal),
            dependencies=list(raw.get("dependencies", []) or []),
            capabilities=list(raw.get("required_capabilities", []) or []),
            required_ability=str(raw.get("required_ability", "") or ""),
            inputs=dict(raw.get("inputs", {}) or {}),
            expected_output=str(raw.get("expected_output", "") or ""),
        )
        # The model's own verification text strengthens (never replaces)
        # the deterministic per-capability criteria.
        proposed = str(raw.get("verification", "") or "").strip()
        if proposed and proposed not in built["verification_criteria"]:
            built["verification_criteria"] = [proposed] + built["verification_criteria"]
        steps.append(built)
    return steps


def topological_order(steps: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Order steps so dependencies precede dependents (stable, deterministic).

    Returns (ordered, problems). Unknown ids and cycles are reported, not
    executed — validation rejects them before execution regardless.
    """
    by_id = {str(s.get("step_id", "")): s for s in steps}
    problems: List[str] = []
    for step in steps:
        for dep in step.get("dependencies", []) or []:
            if str(dep) not in by_id:
                problems.append(f"unknown dependency: {dep!r}")
    if problems:
        return list(steps), problems
    ordered: List[Dict[str, Any]] = []
    permanent: set = set()
    temporary: set = []
    cyclic: List[str] = []

    def visit(sid: str, trail: List[str]) -> None:
        if sid in permanent or sid in cyclic:
            return
        if sid in temporary:
            cyclic.extend(t for t in trail[trail.index(sid):] if t not in cyclic)
            return
        temporary.append(sid)
        for dep in by_id[sid].get("dependencies", []) or []:
            visit(str(dep), trail + [str(dep)])
        temporary.remove(sid)
        permanent.add(sid)
        ordered.append(by_id[sid])

    for sid in by_id:
        visit(sid, [sid])
    if cyclic:
        return list(steps), [f"circular dependency: {sorted(cyclic)}"]
    return ordered, []


def build_memory_context(experiences: List[Dict[str, Any]],
                         procedures: List[Dict[str, Any]],
                         facts: Dict[str, str],
                         max_chars: int = 800) -> str:
    """Bounded advisory context for the planner (never the whole store)."""
    lines: List[str] = []
    for entry in (experiences or [])[:3]:
        lesson = str((entry or {}).get("lesson", ""))[:160]
        outcome = str((entry or {}).get("outcome", ""))
        if lesson:
            lines.append(f"- past {outcome}: {lesson}")
    for proc in (procedures or [])[:2]:
        steps = (proc or {}).get("steps", []) or []
        if steps:
            lines.append("- reusable procedure: " + "; ".join(str(s)[:80] for s in steps[:4]))
    for topic, info in list((facts or {}).items())[:3]:
        lines.append(f"- known fact [{topic}]: {str(info)[:120]}")
    return "\n".join(lines)[:max_chars]


def summarize_observation(outcome: Any) -> str:
    """Concise observation summary for adaptive replanning (no raw dumps)."""
    if not isinstance(outcome, dict):
        return str(outcome)[:200]
    if outcome.get("status") == "success":
        result = outcome.get("result")
        if isinstance(result, dict):
            keys = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(result.items())[:4])
            return f"success: {keys}"[:200]
        return f"success: {str(result)[:160]}"
    errors = outcome.get("errors", []) or []
    return "failed: " + "; ".join(str(e)[:100] for e in errors[:2])[:200]


CognitiveReplanFn = Callable[[Dict[str, Any], str], List[str]]
