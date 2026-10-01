from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Relationships (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured relationships (never free-form strings): a constrained
relation vocabulary with stable ``<source>:<relation>:<target>`` ids.
"""

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Dict

from world.state import utc_now_iso

RELATIONS = (
    "contains", "belongs_to", "runs_on", "located_in", "depends_on",
    "manages", "created_by", "part_of", "uses", "observes",
)


def relationship_id(source_id: str, relation: str, target_id: str) -> str:
    raw = f"{source_id}\x00{relation}\x00{target_id}"
    return (f"{source_id}:{relation}:{target_id}:"
            f"{hashlib.sha256(raw.encode()).hexdigest()[:8]}")


@dataclass
class Relationship:
    id: str = ""
    source_id: str = ""
    relation: str = ""
    target_id: str = ""
    source: str = ""
    confidence: float = 0.5
    created_at: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Relationship":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in dict(data or {}).items() if k in known}
        relationship = cls()
        for key, value in clean.items():
            try:
                setattr(relationship, key, value)
            except Exception:
                pass
        return relationship


def build_relationship(source_id: str, relation: str, target_id: str,
                       source: str = "", confidence: float = 0.5) -> Relationship:
    if relation not in RELATIONS:
        raise ValueError(f"unknown relation: {relation!r} "
                         f"(known: {list(RELATIONS)})")
    if not str(source_id or "").strip() or not str(target_id or "").strip():
        raise ValueError("relationship needs source and target ids")
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        raise ValueError("confidence must be numeric")
    if not (0.0 <= conf <= 1.0):
        raise ValueError("confidence must be 0..1")
    return Relationship(
        id=relationship_id(source_id, relation, target_id),
        source_id=str(source_id), relation=relation,
        target_id=str(target_id), source=str(source or "")[:120],
        confidence=conf, created_at=utc_now_iso(),
    )
