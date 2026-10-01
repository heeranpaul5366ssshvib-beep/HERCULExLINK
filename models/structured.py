from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Structured Model Output
Author: Heeran Paul
License: MIT
--------------------------------------------

Strict parser/validator for model-generated structured intent.

Expected envelope::

    {"intent": str, "goal": str, "reasoning_summary": str,
     "capabilities": [str, ...], "arguments": {str: ...}}

Rules:

* JSON may be raw or fenced (```json ... ```); anything else fails.
* ``intent``/``goal`` must be non-empty strings (length-capped).
* ``reasoning_summary`` must be a string (kept, never executed).
* ``capabilities`` must be a non-empty list of CANONICAL capability
  names (validated against the Capability enum — never invented).
* ``arguments`` must be a mapping of JSON scalars only (no nested
  code, no executable content smuggling).
* Invalid output fails safely with a structured error; NOTHING parsed
  here ever reaches execution without passing the deterministic
  capability/policy/verification pipeline.
"""

import json
import re
from typing import Any, Dict, List, Tuple

REQUIRED_FIELDS = ("intent", "goal", "reasoning_summary", "capabilities", "arguments")

MAX_FIELD_CHARS = 2000
MAX_CAPABILITIES = 8
MAX_ARGUMENTS = 16

# Cognitive plan envelope (Stage 8): model-proposed multi-step plans.
# Steps are advisory until they pass plan validation + registry/policy.
# Only identity/structure/capabilities are mandatory; ability hints,
# inputs, outputs, verification text, and risk are optional — the
# deterministic layer supplies safe defaults for anything omitted.
PLAN_REQUIRED_FIELDS = ("goal", "steps")
PLAN_STEP_REQUIRED_FIELDS = ("step_id", "goal", "dependencies",
                             "required_capabilities")
PLAN_STEP_OPTIONAL_FIELDS = ("required_ability", "inputs", "expected_output",
                             "verification", "risk")
MAX_PLAN_STEPS = 8
VALID_RISKS = ("LOW", "MEDIUM", "HIGH")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _canonical_capabilities() -> List[str]:
    try:
        from cognition.capabilities.capability import Capability
        return [c.value for c in Capability]
    except Exception:
        return []


def extract_json(text: str) -> Tuple[bool, Any, str]:
    """Extract a JSON value from raw or fenced model text."""
    candidate = str(text or "").strip()
    if not candidate:
        return False, None, "empty model output"
    match = _FENCE_RE.search(candidate)
    if match:
        candidate = match.group(1).strip()
    if not candidate:
        return False, None, "empty model output"
    try:
        return True, json.loads(candidate), ""
    except Exception as exc:
        # Retry on the first {...} span (models often add chatter).
        start, end = candidate.find("{"), candidate.rfind("}")
        if 0 <= start < end:
            try:
                return True, json.loads(candidate[start:end + 1]), ""
            except Exception:
                pass
        return False, None, f"output is not valid JSON: {exc}"


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def validate_structured_intent(data: Any) -> Tuple[bool, Dict[str, Any], str]:
    """Validate a parsed envelope. Returns (ok, clean, error)."""
    if not isinstance(data, dict):
        return False, {}, "envelope must be a JSON object"
    for field_name in REQUIRED_FIELDS:
        if field_name not in data:
            return False, {}, f"missing required field: {field_name}"
    intent = data.get("intent")
    goal = data.get("goal")
    summary = data.get("reasoning_summary")
    capabilities = data.get("capabilities")
    arguments = data.get("arguments")
    if not isinstance(intent, str) or not intent.strip():
        return False, {}, "field 'intent' must be a non-empty string"
    if not isinstance(goal, str) or not goal.strip():
        return False, {}, "field 'goal' must be a non-empty string"
    if not isinstance(summary, str):
        return False, {}, "field 'reasoning_summary' must be a string"
    if not isinstance(capabilities, list) or not capabilities:
        return False, {}, "field 'capabilities' must be a non-empty list"
    if len(capabilities) > MAX_CAPABILITIES:
        return False, {}, f"field 'capabilities' exceeds {MAX_CAPABILITIES} entries"
    known = set(_canonical_capabilities())
    clean_caps: List[str] = []
    for cap in capabilities:
        if not isinstance(cap, str):
            return False, {}, f"capability entries must be strings, got {type(cap).__name__}"
        normalized = cap.strip().upper()
        if known and normalized not in known:
            return False, {}, f"unknown capability: {cap!r}"
        if normalized not in clean_caps:
            clean_caps.append(normalized)
    if not isinstance(arguments, dict):
        return False, {}, "field 'arguments' must be an object"
    if len(arguments) > MAX_ARGUMENTS:
        return False, {}, f"field 'arguments' exceeds {MAX_ARGUMENTS} entries"
    clean_args: Dict[str, Any] = {}
    for key, value in arguments.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 64:
            return False, {}, f"invalid argument name: {key!r}"
        if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
            return False, {}, f"argument {key!r} exceeds length limit"
        if not _is_scalar(value):
            return False, {}, f"argument {key!r} must be a scalar (no nested objects)"
        clean_args[key.strip()] = value
    return True, {
        "intent": intent.strip()[:MAX_FIELD_CHARS],
        "goal": goal.strip()[:MAX_FIELD_CHARS],
        "reasoning_summary": summary.strip()[:MAX_FIELD_CHARS],
        "capabilities": clean_caps,
        "arguments": clean_args,
    }, ""


def parse_structured_intent(text: str) -> Tuple[bool, Dict[str, Any], str]:
    """Extract + validate a model-generated intent envelope."""
    ok, data, error = extract_json(text)
    if not ok:
        return False, {}, error
    return validate_structured_intent(data)


def validate_cognitive_plan(data: Any, ability_names: Tuple[str, ...] = ()) -> Tuple[bool, Dict[str, Any], str]:
    """Validate a model-proposed multi-step plan envelope.

    Checks structure only: goal, unique step ids, known capabilities,
    registered abilities (when a name is given), scalar inputs, risk
    enum, per-step verification text. Dependency existence/acyclicity,
    provider coverage, and permissions are enforced later by plan
    validation — a structurally valid proposal can still be rejected.
    Returns (ok, clean, error).
    """
    if not isinstance(data, dict):
        return False, {}, "plan envelope must be a JSON object"
    for field_name in PLAN_REQUIRED_FIELDS:
        if field_name not in data:
            return False, {}, f"missing required field: {field_name}"
    goal = data.get("goal")
    steps = data.get("steps")
    if not isinstance(goal, str) or not goal.strip():
        return False, {}, "field 'goal' must be a non-empty string"
    if not isinstance(steps, list) or not steps:
        return False, {}, "field 'steps' must be a non-empty list"
    if len(steps) > MAX_PLAN_STEPS:
        return False, {}, f"field 'steps' exceeds {MAX_PLAN_STEPS} entries"
    known_caps = set(_canonical_capabilities())
    known_abilities = {str(n).lower() for n in (ability_names or [])}
    seen_ids: List[str] = []
    clean_steps: List[Dict[str, Any]] = []
    for index, raw in enumerate(steps):
        where = f"steps[{index}]"
        if not isinstance(raw, dict):
            return False, {}, f"{where} must be an object"
        for field_name in PLAN_STEP_REQUIRED_FIELDS:
            if field_name not in raw:
                return False, {}, f"{where} missing required field: {field_name}"
        for field_name in PLAN_STEP_OPTIONAL_FIELDS:
            if field_name in raw and raw[field_name] is None and field_name != "required_ability":
                return False, {}, f"{where}.{field_name} must not be null"
        step_id = raw.get("step_id")
        step_goal = raw.get("goal")
        dependencies = raw.get("dependencies")
        capabilities = raw.get("required_capabilities")
        required_ability = raw.get("required_ability")
        inputs = raw.get("inputs", {})
        expected_output = raw.get("expected_output", "")
        verification = raw.get("verification", "")
        risk = raw.get("risk", "LOW")
        if not isinstance(step_id, str) or not step_id.strip():
            return False, {}, f"{where}.step_id must be a non-empty string"
        step_id = step_id.strip()[:64]
        if step_id in seen_ids:
            return False, {}, f"duplicate step_id: {step_id!r}"
        seen_ids.append(step_id)
        if not isinstance(step_goal, str) or not step_goal.strip():
            return False, {}, f"{where}.goal must be a non-empty string"
        if not isinstance(dependencies, list) or any(not isinstance(d, str) for d in dependencies):
            return False, {}, f"{where}.dependencies must be a list of step-id strings"
        if not isinstance(capabilities, list) or not capabilities:
            return False, {}, f"{where}.required_capabilities must be a non-empty list"
        if len(capabilities) > MAX_CAPABILITIES:
            return False, {}, f"{where}.required_capabilities exceeds {MAX_CAPABILITIES} entries"
        clean_caps: List[str] = []
        for cap in capabilities:
            if not isinstance(cap, str):
                return False, {}, f"{where}.required_capabilities entries must be strings"
            normalized = cap.strip().upper()
            if known_caps and normalized not in known_caps:
                return False, {}, f"{where} unknown capability: {cap!r}"
            if normalized not in clean_caps:
                clean_caps.append(normalized)
        clean_ability = ""
        if required_ability not in (None, ""):
            if not isinstance(required_ability, str):
                return False, {}, f"{where}.required_ability must be a string or null"
            clean_ability = required_ability.strip()
            if known_abilities and clean_ability.lower() not in known_abilities:
                return False, {}, f"{where} nonexistent ability: {required_ability!r}"
        if not isinstance(inputs, dict):
            return False, {}, f"{where}.inputs must be an object"
        if len(inputs) > MAX_ARGUMENTS:
            return False, {}, f"{where}.inputs exceeds {MAX_ARGUMENTS} entries"
        clean_inputs: Dict[str, Any] = {}
        for key, value in inputs.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                return False, {}, f"{where} invalid input name: {key!r}"
            if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
                return False, {}, f"{where} input {key!r} exceeds length limit"
            if not _is_scalar(value):
                return False, {}, f"{where} input {key!r} must be a scalar"
            clean_inputs[key.strip()] = value
        if not isinstance(expected_output, str):
            return False, {}, f"{where}.expected_output must be a string"
        if not isinstance(verification, str):
            return False, {}, f"{where}.verification must be a string"
        if not isinstance(risk, str) or not risk.strip():
            risk = "LOW"
        if risk.strip().upper() not in VALID_RISKS:
            return False, {}, f"{where}.risk must be one of {', '.join(VALID_RISKS)}"
        clean_steps.append({
            "step_id": step_id,
            "goal": step_goal.strip()[:MAX_FIELD_CHARS],
            "dependencies": [d.strip() for d in dependencies if d.strip()],
            "required_capabilities": clean_caps,
            "required_ability": clean_ability,
            "inputs": clean_inputs,
            "expected_output": expected_output.strip()[:MAX_FIELD_CHARS],
            "verification": verification.strip()[:MAX_FIELD_CHARS],
            "risk": risk.strip().upper(),
        })
    return True, {"goal": goal.strip()[:MAX_FIELD_CHARS], "steps": clean_steps}, ""


def parse_cognitive_plan(text: str, ability_names: Tuple[str, ...] = ()) -> Tuple[bool, Dict[str, Any], str]:
    """Extract + validate a model-generated multi-step plan envelope."""
    ok, data, error = extract_json(text)
    if not ok:
        return False, {}, error
    return validate_cognitive_plan(data, ability_names)
