from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Observations (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Every world-model mutation originates from an Observation: source,
timestamp, confidence, evidence, affected entity, and the previous
state where one existed. Unverified model assumptions are recorded
as INFERRED at best — never as facts.
"""

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from world.state import FactStatus, utc_now_epoch, utc_now_iso

OBSERVATION_SOURCES = (
    "user", "filesystem", "diagnostics", "vision", "screenshot",
    "computer-use", "task", "memory", "sensor",
)


@dataclass
class Observation:
    id: str = ""
    source: str = ""
    timestamp: str = ""
    epoch: float = 0.0
    confidence: float = 0.5
    evidence: str = ""
    entity_id: str = ""
    entity_type: str = ""
    entity_name: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    status: str = FactStatus.OBSERVED.value
    verified: bool = False
    previous_state: Optional[Dict[str, Any]] = None
    supersedes: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Observation":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in dict(data or {}).items() if k in known}
        observation = cls()
        for key, value in clean.items():
            try:
                setattr(observation, key, value)
            except Exception:
                pass
        return observation


def build_observation(source: str, entity_type: str, entity_name: str,
                      properties=None, evidence: str = "",
                      confidence: float = 0.5,
                      status: str = FactStatus.OBSERVED.value,
                      verified: bool = False) -> Observation:
    if source not in OBSERVATION_SOURCES:
        raise ValueError(f"unknown observation source: {source!r} "
                         f"(known: {list(OBSERVATION_SOURCES)})")
    if status not in [s.value for s in FactStatus]:
        raise ValueError(f"unknown fact status: {status!r}")
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        raise ValueError("confidence must be numeric")
    if not (0.0 <= conf <= 1.0):
        raise ValueError("confidence must be 0..1")
    from world.entity import entity_id as _entity_id

    return Observation(
        id=f"obs-{uuid.uuid4().hex[:12]}",
        source=source,
        timestamp=utc_now_iso(),
        epoch=utc_now_epoch(),
        confidence=conf,
        evidence=str(evidence or "")[:500],
        entity_id=_entity_id(entity_type, entity_name),
        entity_type=entity_type,
        entity_name=str(entity_name or "").strip()[:200],
        properties=dict(properties or {}),
        status=status,
        verified=bool(verified),
    )
