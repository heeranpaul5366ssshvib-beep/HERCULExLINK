from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Failure Taxonomy & Learning
Author: Heeran Paul
License: MIT
--------------------------------------------

One standardized category set used consistently in logs, metrics,
recovery and reports:

INPUT / CONTEXT / RETRIEVAL / MODEL / PLANNING / TOOL / PERMISSION /
RESOURCE / NETWORK / PERSISTENCE / VERIFICATION / INTERNAL

``FailureLedger`` aggregates recurring failures so aggregate data —
never a single anecdote — drives engineering improvements.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class FailureCategory(str, Enum):
    INPUT = "input"
    CONTEXT = "context"
    RETRIEVAL = "retrieval"
    MODEL = "model"
    PLANNING = "planning"
    TOOL = "tool"
    PERMISSION = "permission"
    RESOURCE = "resource"
    NETWORK = "network"
    PERSISTENCE = "persistence"
    VERIFICATION = "verification"
    INTERNAL = "internal"


_SEVERITY: Dict[FailureCategory, str] = {
    FailureCategory.INPUT: "fatal",
    FailureCategory.CONTEXT: "retryable",
    FailureCategory.RETRIEVAL: "retryable",
    FailureCategory.MODEL: "retryable",
    FailureCategory.PLANNING: "retryable",
    FailureCategory.TOOL: "retryable",
    FailureCategory.PERMISSION: "fatal",
    FailureCategory.RESOURCE: "retryable",
    FailureCategory.NETWORK: "retryable",
    FailureCategory.PERSISTENCE: "retryable",
    FailureCategory.VERIFICATION: "fatal",
    FailureCategory.INTERNAL: "fatal",
}

_PATTERNS = (
    (("permission", "denied", "not allowed", "forbidden", "unauthorized"), FailureCategory.PERMISSION, "PERMISSION_DENIED"),
    (("model", "adapter", "ollama", "unavailable model"), FailureCategory.MODEL, "MODEL_UNAVAILABLE"),
    (("timeout", "timed out"), FailureCategory.NETWORK, "TIMEOUT"),
    (("retriev", "not found", "no results", "empty retrieval", "index"), FailureCategory.RETRIEVAL, "RETRIEVAL_MISS"),
    (("rout",), FailureCategory.MODEL, "ROUTING_ERROR"),
    (("retr", "exhausted", "maximum retries"), FailureCategory.PLANNING, "RECOVERY_EXHAUSTED"),
    (("plan", "invalid step", "dependency"), FailureCategory.PLANNING, "PLANNING_INVALID"),
    (("tool", "ability"), FailureCategory.TOOL, "TOOL_FAILURE"),
    (("verif", "expected", "mismatch"), FailureCategory.VERIFICATION, "VERIFICATION_FAILED"),
    (("persist", "storage", "save", "load"), FailureCategory.PERSISTENCE, "PERSISTENCE_ERROR"),
    (("resource", "memory", "out of", "overload"), FailureCategory.RESOURCE, "RESOURCE_EXHAUSTED"),
    (("network", "connection", "unreachable"), FailureCategory.NETWORK, "NETWORK_ERROR"),
    (("context", "budget", "token"), FailureCategory.CONTEXT, "CONTEXT_OVERFLOW"),
    (("input", "invalid", "malformed", "missing"), FailureCategory.INPUT, "INVALID_INPUT"),
)

_CODE_SEVERITY = {
    "RECOVERY_EXHAUSTED": "fatal",  # retries already spent; do not loop
}


@dataclass
class FailureRecord:
    code: str
    category: FailureCategory
    severity: str  # fatal | retryable
    retryable: bool
    message: str = ""
    task_id: str = ""
    correlation_id: str = ""
    timestamp: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category.value,
            "severity": self.severity,
            "retryable": self.retryable,
            "message": self.message,
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "detail": dict(self.detail),
        }


def classify_failure(
    error: Any,
    task_id: str = "",
    correlation_id: str = "",
    category_hint: Optional[FailureCategory] = None,
) -> FailureRecord:
    """Classify free-text errors into the standard taxonomy."""
    message = str(error or "unknown error")
    lowered = message.lower()
    category = category_hint or FailureCategory.INTERNAL
    code = "INTERNAL_ERROR"
    if category_hint is None:
        for keywords, candidate, candidate_code in _PATTERNS:
            if any(keyword in lowered for keyword in keywords):
                category, code = candidate, candidate_code
                break
    else:
        code = f"{category.value.upper()}_ERROR"
    severity = _CODE_SEVERITY.get(code, _SEVERITY[category])
    return FailureRecord(
        code=code,
        category=category,
        severity=severity,
        retryable=(severity == "retryable"),
        message=message,
        task_id=task_id,
        correlation_id=correlation_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


class FailureLedger:
    """Aggregate failures; surface recurring ones for engineering action."""

    def __init__(self):
        self._records: List[FailureRecord] = []

    def record(self, failure: FailureRecord) -> FailureRecord:
        self._records.append(failure)
        return failure

    def record_error(self, error: Any, **kwargs: Any) -> FailureRecord:
        return self.record(classify_failure(error, **kwargs))

    def top_recurring(self, limit: int = 5) -> List[Dict[str, Any]]:
        counts = Counter((r.category.value, r.code) for r in self._records)
        return [
            {"category": category, "code": code, "count": count}
            for (category, code), count in counts.most_common(max(0, limit))
        ]

    def recovery_rate(self) -> float:
        """Share of retryable failures (recoverable class); 1.0 when empty."""
        if not self._records:
            return 1.0
        retryable = sum(1 for r in self._records if r.retryable)
        return retryable / len(self._records)

    def statistics(self) -> Dict[str, Any]:
        by_category = Counter(r.category.value for r in self._records)
        return {
            "total": len(self._records),
            "by_category": dict(by_category),
            "recovery_rate": round(self.recovery_rate(), 3),
            "top_recurring": self.top_recurring(),
        }


_EMBEDDING_CODE_MAP = {
    "EMBEDDING_UNAVAILABLE": (FailureCategory.MODEL, "MODEL_UNAVAILABLE", "retryable"),
    "EMBEDDING_DIMENSION_MISMATCH": (FailureCategory.MODEL, "EMBEDDING_DIMENSION_MISMATCH", "retryable"),
    "EMBEDDING_MALFORMED": (FailureCategory.INTERNAL, "EMBEDDING_MALFORMED", "fatal"),
    "EMBEDDING_ERROR": (FailureCategory.MODEL, "MODEL_UNAVAILABLE", "retryable"),
}


def classify_embedding_error(
    error: Any,
    task_id: str = "",
    correlation_id: str = "",
) -> FailureRecord:
    """Classify embedding/provider failures with the existing taxonomy.

    Matches the provider ``code`` attribute (no import of the models
    layer needed); anything unrecognized falls back to the standard
    free-text classifier. No new failure categories are introduced.
    """
    code = str(getattr(error, "code", "") or "").upper()
    message = str(error or "unknown embedding error")
    if code in _EMBEDDING_CODE_MAP:
        category, mapped_code, severity = _EMBEDDING_CODE_MAP[code]
        return FailureRecord(
            code=mapped_code,
            category=category,
            severity=severity,
            retryable=(severity == "retryable"),
            message=message,
            task_id=task_id,
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    return classify_failure(error, task_id=task_id, correlation_id=correlation_id)
