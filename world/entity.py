from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Entities (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured entities with stable IDs (``<type>:<slug>``). No entity
exists without evidence: every create/update carries source +
confidence, and validation rejects malformed input loudly.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

from world.state import FactStatus, utc_now_epoch, utc_now_iso

ENTITY_TYPES = (
    "person", "device", "application", "file", "folder", "project",
    "task", "goal", "location", "object", "environment",
)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:120] or "unnamed"


def entity_id(entity_type: str, name: str) -> str:
    return f"{entity_type}:{_slug(name)}"


@dataclass
class Entity:
    id: str = ""
    type: str = ""
    name: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    confidence: float = 0.5
    status: str = FactStatus.OBSERVED.value
    created_at: str = ""
    updated_at: str = ""
    last_verified: float = 0.0
    stale: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entity":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in dict(data or {}).items() if k in known}
        entity = cls()
        for key, value in clean.items():
            try:
                setattr(entity, key, value)
            except Exception:
                pass
        return entity


def validate_entity(entity_type: str, name: str, confidence: float = 0.5,
                    status: str = FactStatus.OBSERVED.value) -> None:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type: {entity_type!r} "
                         f"(known: {list(ENTITY_TYPES)})")
    if not str(name or "").strip():
        raise ValueError("entity needs a non-empty name")
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        raise ValueError("confidence must be numeric")
    if not (0.0 <= conf <= 1.0):
        raise ValueError("confidence must be 0..1")
    if status not in [s.value for s in FactStatus]:
        raise ValueError(f"unknown fact status: {status!r}")


def build_entity(entity_type: str, name: str, properties=None,
                 source: str = "", confidence: float = 0.5,
                 status: str = FactStatus.OBSERVED.value,
                 verified: bool = False) -> Entity:
    validate_entity(entity_type, name, confidence, status)
    now = utc_now_iso()
    clean_props = {str(k)[:80]: v for k, v in dict(properties or {}).items()}
    return Entity(
        id=entity_id(entity_type, name),
        type=entity_type,
        name=str(name).strip()[:200],
        properties=clean_props,
        source=str(source or "")[:120],
        confidence=float(confidence),
        status=status if not verified else FactStatus.KNOWN.value,
        created_at=now,
        updated_at=now,
        last_verified=utc_now_epoch() if verified else 0.0,
    )


def merge_entities(current: Entity, incoming: Entity) -> Entity:
    """Fold new evidence in: properties merge, confidence takes the max
    of corroborating evidence, verification timestamp refreshes only on
    verified input. History is preserved by the observation log."""
    current.properties.update(incoming.properties)
    current.confidence = min(1.0, max(current.confidence, incoming.confidence))
    current.updated_at = utc_now_iso()
    if incoming.last_verified:
        current.last_verified = incoming.last_verified
        current.stale = False
    if incoming.source and incoming.source not in (current.source or ""):
        current.source = f"{current.source}+{incoming.source}"[:120]
    return current


def entity_summary(entity: Entity) -> str:
    where = ""
    for key in ("path", "location", "address", "window"):
        if entity.properties.get(key):
            where = f" at {entity.properties[key]}"
            break
    return f"{entity.type} {entity.name!r}{where} [{entity.status}]"
