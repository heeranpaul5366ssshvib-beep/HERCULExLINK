from __future__ import annotations
"""Structured failure records + rule-based classification (6U §1).

Classification is evidence-driven and deterministic. When evidence is
insufficient the type is UNKNOWN with low confidence — causes are
never invented.
"""

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class FailureType(str, Enum):
    TOOL_ERROR = "TOOL_ERROR"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    WRONG_ASSUMPTION = "WRONG_ASSUMPTION"
    PLANNING_ERROR = "PLANNING_ERROR"
    STATE_MISREAD = "STATE_MISREAD"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    DATA_ERROR = "DATA_ERROR"
    ENVIRONMENT_CHANGE = "ENVIRONMENT_CHANGE"
    TIMEOUT = "TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    MODEL_ERROR = "MODEL_ERROR"
    UNKNOWN = "UNKNOWN"


FAILURE_TYPES = [t.value for t in FailureType]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_hash(state: Dict[str, Any]) -> str:
    import json

    blob = json.dumps(state or {}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class FailureRecord:
    task_id: str
    goal: str
    plan: List[str] = field(default_factory=list)
    step_id: str = ""
    attempted_action: str = ""
    tool: str = ""
    input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    expected_result: str = ""
    actual_result: str = ""
    failure_type: str = FailureType.UNKNOWN.value
    failure_reason: str = ""
    confidence: float = 0.0
    recovery_action: str = ""
    retry_count: int = 0
    final_outcome: str = "open"
    timestamp: str = field(default_factory=_utcnow)
    environment_state_hash: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_failure(observation: str = "", error: str = "",
                     expected: str = "", actual: str = "",
                     tool: str = "", permission: Optional[bool] = None,
                     timed_out: bool = False) -> Dict[str, Any]:
    """Rule-based classifier. Returns {type, reason, confidence}.

    Confidence is high only for direct evidence (explicit error
    strings, permission verdicts, timeouts). Ambiguous cases yield
    UNKNOWN at low confidence.
    """
    obs = f"{observation} {error}".lower()
    if timed_out or "timeout" in obs or "timed out" in obs:
        return {"type": FailureType.TIMEOUT.value,
                "reason": "timeout signal in observation/error",
                "confidence": 0.9}
    if permission is False or "permission denied" in obs or "not authorized" in obs:
        return {"type": FailureType.PERMISSION_DENIED.value,
                "reason": "explicit permission denial",
                "confidence": 0.95}
    if any(k in obs for k in ("invalid argument", "unexpected argument",
                              "unknown parameter", "schema", "validation error",
                              "missing required")):
        return {"type": FailureType.INVALID_ARGUMENT.value,
                "reason": "argument/schema complaint in tool output",
                "confidence": 0.85}
    if any(k in obs for k in ("not found", "no such", "does not exist",
                              "connection", "unreachable", "changed")):
        return {"type": FailureType.ENVIRONMENT_CHANGE.value,
                "reason": "environment state differs from expectation",
                "confidence": 0.7}
    if any(k in obs for k in ("traceback", "exception", "error:", "failed")):
        return {"type": FailureType.TOOL_ERROR.value,
                "reason": "tool raised an error",
                "confidence": 0.8}
    if expected and actual is not None and str(expected) != str(actual) \
            and not obs.strip():
        return {"type": FailureType.VERIFICATION_FAILURE.value,
                "reason": "result mismatch without error signal",
                "confidence": 0.6}
    if tool and not obs.strip():
        return {"type": FailureType.UNKNOWN.value,
                "reason": "no error signal; cause not inferable",
                "confidence": 0.2}
    return {"type": FailureType.UNKNOWN.value,
            "reason": "insufficient evidence",
            "confidence": 0.1}


def build_record(task_id: str, goal: str, action: Dict[str, Any],
                 observation: str, expected: str = "",
                 environment: Dict[str, Any] | None = None,
                 **hints) -> FailureRecord:
    verdict = classify_failure(
        observation=observation, expected=expected,
        actual=observation, tool=str(action.get("tool", "")), **hints)
    return FailureRecord(
        task_id=str(task_id), goal=str(goal),
        plan=[str(s) for s in (action.get("plan") or [])],
        step_id=str(action.get("step_id", "")),
        attempted_action=str(action.get("action", "")),
        tool=str(action.get("tool", "")),
        input=dict(action.get("input") or {}),
        observation=str(observation), expected_result=str(expected),
        actual_result=str(observation),
        failure_type=verdict["type"], failure_reason=verdict["reason"],
        confidence=float(verdict["confidence"]),
        environment_state_hash=_state_hash(environment or {}))
