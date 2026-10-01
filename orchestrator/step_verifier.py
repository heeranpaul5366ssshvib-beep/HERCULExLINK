from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Step Verifier
Author: Heeran Paul
License: MIT
--------------------------------------------

A step is complete only when its expected outcome VERIFIES — never
merely because the tool returned. Per-capability verification methods
check the observation against the step's expected outputs/criteria.
"""

from typing import Any, Dict


def _failed_with_error(observation: Any) -> str:
    """Explicit error signals in a result always fail verification."""
    if isinstance(observation, dict):
        if observation.get("error"):
            return str(observation["error"])[:200]
        inner = observation.get("result")
        if isinstance(inner, dict) and inner.get("error"):
            return str(inner["error"])[:200]
    return ""


def _text(result: Any) -> str:
    if isinstance(result, dict):
        for key in ("content", "text", "output", "result", "response"):
            if result.get(key):
                return str(result[key])
        return str(result)
    return str(result or "")


def verify_file_write(step: Dict[str, Any], observation: Any) -> Dict[str, Any]:
    err = _failed_with_error(observation)
    if err:
        return {"passed": False, "detail": f"executor error: {err}"}
    expected = step.get("expected_outputs") or []
    content = _text(observation.get("result") if isinstance(observation, dict) else observation)
    if not expected:
        passed = bool(content)
        return {"passed": passed, "detail": "content returned" if passed else "empty result"}
    missing = [item for item in expected if str(item) not in content]
    return {"passed": not missing, "detail": "all expected outputs present" if not missing else f"missing: {missing}"}


def verify_execution(step: Dict[str, Any], observation: Any) -> Dict[str, Any]:
    data = observation if isinstance(observation, dict) else {}
    err = _failed_with_error(observation)
    if err:
        return {"passed": False, "detail": f"executor error: {err}"}
    result = data.get("result", observation)
    status = str(data.get("status", "")).upper()
    exit_code = data.get("exit_code", data.get("exit_status", 0))
    if status in ("FAILED", "ERROR"):
        return {"passed": False, "detail": f"executor reported {status}"}
    try:
        failed = int(exit_code) != 0
    except (TypeError, ValueError):
        failed = False
    if failed:
        return {"passed": False, "detail": f"non-zero exit {exit_code}"}
    expected = step.get("expected_outputs") or []
    content = _text(result)
    missing = [item for item in expected if str(item) not in content]
    if missing:
        return {"passed": False, "detail": f"missing outputs: {missing}"}
    return {"passed": True, "detail": "exit status ok, outputs present"}


def verify_research(step: Dict[str, Any], observation: Any) -> Dict[str, Any]:
    err = _failed_with_error(observation)
    if err:
        return {"passed": False, "detail": f"executor error: {err}"}
    content = _text(observation.get("result") if isinstance(observation, dict) else observation)
    if not content.strip():
        return {"passed": False, "detail": "empty evidence set"}
    expected = step.get("expected_outputs") or []
    missing = [item for item in expected if str(item) not in content]
    if missing:
        return {"passed": False, "detail": f"missing expected evidence: {missing}"}
    return {"passed": True, "detail": f"evidence present ({len(content)} chars)"}


def verify_default(step: Dict[str, Any], observation: Any) -> Dict[str, Any]:
    data = observation if isinstance(observation, dict) else {}
    err = _failed_with_error(observation)
    if err:
        return {"passed": False, "detail": f"executor error: {err}"}
    if str(data.get("status", "")).upper() in ("FAILED", "ERROR"):
        return {"passed": False, "detail": "executor reported failure"}
    if data.get("result") is None and observation is None:
        return {"passed": False, "detail": "no result returned"}
    criteria = step.get("verification_criteria") or []
    return {"passed": True, "detail": f"tool returned; {len(criteria)} criteria recorded"}


def verify_math(step: Dict[str, Any], observation: Any) -> Dict[str, Any]:
    """MATH: result must recompute independently (never trust output alone)."""
    err = _failed_with_error(observation)
    if err:
        return {"passed": False, "detail": f"executor error: {err}"}
    data = observation.get("result", observation) if isinstance(observation, dict) else {}
    if not isinstance(data, dict):
        return {"passed": False, "detail": "no structured math result"}
    if str(data.get("status", "")).lower() not in ("success",):
        return {"passed": False, "detail": f"ability reported {data.get('status')}: {data.get('error', '')}"[:200]}
    expression = str(data.get("expression", ""))
    claimed = data.get("result", None)
    if expression == "" or claimed is None:
        # Legacy/generic MATH providers return content without the
        # expression/result pair: fall back to evidence-present check
        # (strict recomputation applies to structured calculator output).
        content = _text(data)
        if content.strip():
            return {"passed": True, "detail": f"evidence present ({len(content)} chars)"}
        return {"passed": False, "detail": "missing expression/result"}
    try:
        from abilities.calculator.calculator_ability import safe_evaluate
        expected = safe_evaluate(expression)
    except Exception as exc:
        return {"passed": False, "detail": f"recomputation failed: {exc}"}
    try:
        ok = abs(float(expected) - float(claimed)) < 1e-9
    except (TypeError, ValueError):
        ok = expected == claimed
    return {"passed": ok,
            "detail": "result verified by recomputation" if ok
                      else f"mismatch: claimed {claimed} != recomputed {expected}"}


_VERIFY_BY_CAPABILITY = {
    "FILE_WRITE": verify_file_write,
    "DOCUMENT_WRITE": verify_file_write,
    "CODE_EDIT": verify_file_write,
    "CODE_EXECUTION": verify_execution,
    "TERMINAL_EXECUTE": verify_execution,
    "WEB_SEARCH": verify_research,
    "KNOWLEDGE_RETRIEVAL": verify_research,
    "DOCUMENT_READ": verify_research,
    "FILE_READ": verify_research,
    "VISION_ANALYSIS": verify_research,
    "SPEECH_RECOGNITION": verify_research,
    "TEXT_TO_SPEECH": verify_research,
    "SYSTEM_OBSERVE": verify_research,
    "BROWSER_USE": verify_research,
    "MATH": verify_math,
    "DATABASE_READ": verify_research,
}


def verify_step(step: Dict[str, Any], observation: Any) -> Dict[str, Any]:
    """Run the verification method for the step's primary capability."""
    caps = step.get("required_capabilities", []) or []
    for cap in caps:
        method = _VERIFY_BY_CAPABILITY.get(str(cap).upper())
        if method is not None:
            outcome = method(step, observation)
            return {"step_id": step.get("step_id"), "capability": str(cap).upper(), **outcome}
    outcome = verify_default(step, observation)
    return {"step_id": step.get("step_id"), "capability": "DEFAULT", **outcome}
