from __future__ import annotations
"""Task-state ledger with provenance (6U §4) + scoped lessons (6U §16).

Facts carry {observation, source, confidence, timestamp, scope}.
A single uncertain observation never becomes permanent truth:
writes below ``FIRM_THRESHOLD`` stay provisional and expire.
Scopes: TASK < SESSION < ENVIRONMENT < USER < GLOBAL. Promotion
across scopes requires consolidation (see lessons.py).
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCOPES = ("TASK", "SESSION", "ENVIRONMENT", "USER", "GLOBAL")
FIRM_THRESHOLD = 0.75


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StateFact:
    key: str
    value: str
    observation: str = ""
    source: str = ""
    confidence: float = 0.0
    timestamp: str = field(default_factory=_utcnow)
    scope: str = "TASK"
    provisional: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskStateLedger:
    """Per-task world/task-state with provenance and contradiction flags."""

    def __init__(self, task_id: str, scope: str = "TASK"):
        self.task_id = str(task_id)
        self.scope = scope if scope in SCOPES else "TASK"
        self._facts: Dict[str, StateFact] = {}
        self.contradictions: List[Dict[str, Any]] = []

    def update(self, key: str, value: str, observation: str = "",
               source: str = "", confidence: float = 0.0,
               scope: Optional[str] = None) -> StateFact:
        scope = scope or self.scope
        if scope not in SCOPES:
            raise ValueError(f"invalid scope {scope!r}")
        old = self._facts.get(key)
        if old is not None and old.value != value and old.confidence >= 0.5 \
                and confidence >= 0.5:
            self.contradictions.append({
                "key": key, "old": old.value, "new": value,
                "old_confidence": old.confidence,
                "new_confidence": confidence, "timestamp": _utcnow()})
        fact = StateFact(key=key, value=value, observation=observation,
                         source=source, confidence=float(confidence),
                         scope=scope,
                         provisional=float(confidence) < FIRM_THRESHOLD)
        self._facts[key] = fact
        return fact

    def get(self, key: str, default: str = "") -> str:
        fact = self._facts.get(key)
        return fact.value if fact is not None else default

    def firm(self) -> Dict[str, str]:
        return {k: f.value for k, f in self._facts.items() if not f.provisional}

    def as_dict(self) -> Dict[str, Any]:
        return {"task_id": self.task_id, "scope": self.scope,
                "facts": {k: f.as_dict() for k, f in self._facts.items()},
                "contradictions": list(self.contradictions)}
