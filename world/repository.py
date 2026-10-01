from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Repository (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

In-memory entity/relationship/observation store with JSON-file
persistence (atomic tmp+replace, corrupt-backup recovery, bounded
growth). Ingestion rules:

* same id -> merge evidence (no duplicates, ever)
* contradicting properties -> old value kept in the observation's
  previous_state, entity marked fresh (history is never silently
  overwritten; the observation log is the audit trail)
* INFERRED input never overwrites KNOWN/OBSERVED state
"""

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from world.config import WorldConfig, load_world_config
from world.entity import (
    build_entity,
    entity_id,
    merge_entities,
    validate_entity,
)
from world.observation import Observation, build_observation
from world.relationship import build_relationship
from world.state import FactStatus, is_stale, promote, utc_now_epoch

logger = logging.getLogger("HERCULE.World.Repository")


class WorldRepository:
    """Persistent structured world state (current facts, not history)."""

    def __init__(self, path: str = "",
                 config: Optional[WorldConfig] = None):
        self.config = config or load_world_config()
        from world.config import default_store_path

        self.path = Path(path or default_store_path(self.config))
        self.entities: Dict[str, Any] = {}
        self.relationships: Dict[str, Any] = {}
        self.observations: Dict[str, Observation] = {}
        self._order: List[str] = []  # observation arrival order
        self.degraded = False
        self.load()

    # --------------------------------------------------
    # Persistence (atomic writes, corrupt recovery, caps)
    # --------------------------------------------------
    def load(self) -> int:
        from world.entity import Entity
        from world.relationship import Relationship

        self.entities.clear()
        self.relationships.clear()
        self.observations.clear()
        self._order = []
        self.degraded = False
        if not self.path.exists():
            return 0
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            backup = self.path.with_suffix(f".corrupt-{stamp}.bak")
            try:
                self.path.replace(backup)
            except Exception:
                pass
            logger.warning("world store corrupt (%s); backed up, starting empty", exc)
            self.degraded = True
            return 0
        if not isinstance(data, dict):
            self.degraded = True
            return 0
        loaded = 0
        for item in data.get("entities", []) or []:
            try:
                entity = Entity.from_dict(item)
                if entity.id:
                    self.entities[entity.id] = entity
                    loaded += 1
            except Exception:
                continue
        for item in data.get("relationships", []) or []:
            try:
                relationship = Relationship.from_dict(item)
                if relationship.id:
                    self.relationships[relationship.id] = relationship
            except Exception:
                continue
        for item in data.get("observations", []) or []:
            try:
                observation = Observation.from_dict(item)
                if observation.id:
                    self.observations[observation.id] = observation
                    self._order.append(observation.id)
            except Exception:
                continue
        return loaded

    def save(self) -> bool:
        from system.state_guard import check_state_write

        check_state_write(str(self.path), owner="world")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1,
                       "entities": [e.as_dict() for e in self.entities.values()],
                       "relationships": [r.as_dict() for r in self.relationships.values()],
                       "observations": [self.observations[i].as_dict()
                                        for i in self._order
                                        if i in self.observations]}
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with open(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=1)
                Path(tmp).replace(self.path)
            except Exception:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            self.degraded = False
            return True
        except Exception as exc:
            logger.warning("world store save failed: %s", exc)
            self.degraded = True
            return False

    # --------------------------------------------------
    # Observations -> state (the ONLY mutation path)
    # --------------------------------------------------
    def observe(self, source: str, entity_type: str, entity_name: str,
                properties=None, evidence: str = "",
                confidence: float = 0.5,
                status: str = FactStatus.OBSERVED.value,
                verified: bool = False) -> Tuple[Any, Observation]:
        validate_entity(entity_type, entity_name, confidence, status)
        observation = build_observation(
            source, entity_type, entity_name, properties, evidence,
            confidence, status, verified)
        entity = self._apply(observation)
        self.observations[observation.id] = observation
        self._order.append(observation.id)
        self._enforce_caps()
        return entity, observation

    def _apply(self, observation: Observation) -> Any:
        from world.entity import Entity

        current = self.entities.get(observation.entity_id)
        incoming = build_entity(
            observation.entity_type, observation.entity_name,
            observation.properties, observation.source,
            observation.confidence, observation.status,
            verified=observation.verified)
        if current is None:
            self.entities[incoming.id] = incoming
            return incoming
        # INFERRED evidence never demotes established state.
        if (observation.status == FactStatus.INFERRED.value
                and current.status in (FactStatus.KNOWN.value,
                                       FactStatus.OBSERVED.value)):
            observation.previous_state = {"kept": current.status,
                                          "note": "inference did not overwrite"}
            return current
        # Contradictions: snapshot the old properties on the observation.
        clashes = {k: current.properties.get(k) for k, v in incoming.properties.items()
                   if k in current.properties and current.properties[k] != v}
        if clashes:
            observation.previous_state = {"properties": clashes}
        merged = merge_entities(current, incoming)
        merged.status = promote(current.status, observation.verified)
        if observation.verified:
            merged.last_verified = observation.epoch
        merged.stale = False
        return merged

    # --------------------------------------------------
    # Direct entity/relationship management
    # --------------------------------------------------
    def get(self, entity_id: str) -> Optional[Any]:
        return self.entities.get(entity_id)

    def remove_entity(self, entity_id: str) -> bool:
        if entity_id not in self.entities:
            return False
        del self.entities[entity_id]
        self.relationships = {k: r for k, r in self.relationships.items()
                              if r.source_id != entity_id
                              and r.target_id != entity_id}
        return True

    def invalidate(self, entity_id: str, reason: str = "") -> bool:
        entity = self.entities.get(entity_id)
        if entity is None:
            return False
        entity.stale = True
        entity.status = FactStatus.STALE.value
        from world.state import utc_now_iso

        entity.updated_at = utc_now_iso()
        entity.properties["invalidated"] = str(reason or "")[:200]
        return True

    def relate(self, source_id: str, relation: str, target_id: str,
               source: str = "", confidence: float = 0.5) -> Any:
        if source_id not in self.entities:
            raise ValueError(f"unknown source entity: {source_id!r}")
        if target_id not in self.entities:
            raise ValueError(f"unknown target entity: {target_id!r}")
        relationship = build_relationship(source_id, relation, target_id,
                                          source, confidence)
        self.relationships[relationship.id] = relationship
        self._enforce_caps()
        return relationship

    def unrelate(self, relationship_id: str) -> bool:
        return self.relationships.pop(relationship_id, None) is not None

    def neighbors(self, entity_id: str) -> List[Any]:
        return [r for r in self.relationships.values()
                if r.source_id == entity_id or r.target_id == entity_id]

    # --------------------------------------------------
    # Staleness + bounds
    # --------------------------------------------------
    def refresh_stale(self, now: float = 0.0) -> int:
        count = 0
        for entity in self.entities.values():
            if (not entity.stale and entity.last_verified
                    and is_stale(entity.last_verified,
                                 self.config.stale_after_s, now or utc_now_epoch())):
                entity.stale = True
                count += 1
        return count

    def _enforce_caps(self) -> None:
        entities = sorted(self.entities.values(),
                          key=lambda e: (e.updated_at or ""))
        while len(entities) > self.config.max_entities:
            victim = entities.pop(0)
            self.remove_entity(victim.id)
        while len(self._order) > self.config.max_observations:
            oldest = self._order.pop(0)
            self.observations.pop(oldest, None)

    # --------------------------------------------------
    def statistics(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for entity in self.entities.values():
            by_type[entity.type] = by_type.get(entity.type, 0) + 1
        return {"entities": len(self.entities),
                "relationships": len(self.relationships),
                "observations": len(self.observations),
                "by_type": by_type, "path": str(self.path),
                "degraded": self.degraded}

    def recent_observations(self, limit: int = 10) -> List[Observation]:
        return [self.observations[i] for i in self._order[-max(1, limit):]
                if i in self.observations]
