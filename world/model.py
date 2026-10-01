from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Model Facade (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Single entry point over the repository: observations in, bounded
context out. The world model is contextual knowledge only — it never
grants permissions, never executes, never overrides policy. Callers
that need TaskManager authority (task status) get references, not
copies: live task state always wins.
"""

import re
from typing import Any, Dict, List, Optional

from world.config import WorldConfig, load_world_config
from world.repository import WorldRepository
from world.state import FactStatus

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Bounded context budget for LLM prompts (never the whole store).
MAX_CONTEXT_ENTITIES = 8
MAX_CONTEXT_CHARS = 1500


class WorldModel:
    """Persistent structured current-state (facade over WorldRepository)."""

    def __init__(self, path: str = "",
                 config: Optional[WorldConfig] = None):
        self.repo = WorldRepository(path=path, config=config or load_world_config())

    # --------------------------------------------------
    # Observation intake (validated structured input only)
    # --------------------------------------------------
    def observe(self, source: str, entity_type: str, entity_name: str,
                properties=None, evidence: str = "",
                confidence: float = 0.5,
                status: str = FactStatus.OBSERVED.value,
                verified: bool = False, persist: bool = True):
        entity, observation = self.repo.observe(
            source, entity_type, entity_name, properties, evidence,
            confidence, status, verified)
        if persist:
            self.repo.save()
        return entity, observation

    def observe_application(self, name: str, state: str,
                            source: str = "computer-use",
                            evidence: str = "", verified: bool = False,
                            persist: bool = True):
        return self.observe(source, "application", name,
                            {"state": state}, evidence,
                            confidence=0.9 if verified else 0.5,
                            status=(FactStatus.KNOWN.value if verified
                                    else FactStatus.OBSERVED.value),
                            verified=verified, persist=persist)

    def observe_file(self, path: str, exists: bool,
                     source: str = "filesystem", evidence: str = "",
                     persist: bool = True):
        from pathlib import Path as _Path

        name = _Path(str(path)).name or str(path)
        return self.observe(
            source, "file", name, {"path": str(path),
                                   "exists": bool(exists)}, evidence,
            confidence=0.95 if exists else 0.6,
            status=(FactStatus.KNOWN.value if exists
                    else FactStatus.OBSERVED.value),
            verified=bool(exists), persist=persist)

    # --------------------------------------------------
    # Bounded context for reasoning (relevant slice only)
    # --------------------------------------------------
    def context_for(self, query: str, limit: int = MAX_CONTEXT_ENTITIES) -> str:
        """Relevant entities as compact text (bounded, evidence-tagged)."""
        scored = self._relevant(query, limit)
        if not scored:
            return ""
        lines = []
        for entity, _ in scored:
            from world.entity import entity_summary

            lines.append(f"- {entity_summary(entity)} "
                         f"(source={entity.source or 'unknown'})")
        text = "Current world state:\n" + "\n".join(lines)
        return text[:MAX_CONTEXT_CHARS]

    def _relevant(self, query: str, limit: int):
        tokens = set(_TOKEN_RE.findall(str(query or "").lower()))
        if not tokens:
            return []
        scored = []
        for entity in self.repo.entities.values():
            if entity.stale:
                continue
            haystack = set(_TOKEN_RE.findall(
                f"{entity.name} {entity.type} {' '.join(map(str, entity.properties.values()))}".lower()))
            overlap = tokens & haystack
            if not overlap:
                continue
            score = len(overlap) / max(1, len(tokens)) * 0.7 + entity.confidence * 0.3
            scored.append((entity, score))
        scored.sort(key=lambda item: (item[1], item[0].updated_at), reverse=True)
        return scored[:max(1, limit)]

    # --------------------------------------------------
    # Candidate names for reference resolution (verified only)
    # --------------------------------------------------
    def reference_candidates(self, limit: int = 20) -> List[str]:
        """Fresh, non-stale file/object/application names for anaphora."""
        names: List[str] = []
        for entity in self.repo.entities.values():
            if entity.stale or entity.status == FactStatus.INFERRED.value:
                continue
            if entity.type in ("file", "object", "application"):
                label = entity.properties.get("path", "") or entity.name
                if label and label not in names:
                    names.append(str(label))
            if len(names) >= limit:
                break
        return names

    # --------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """HUD/UI state: real counts, never the whole database."""
        stats = self.repo.statistics()
        apps = [e.name for e in self.repo.entities.values()
                if e.type == "application" and not e.stale][:5]
        recent = self.repo.recent_observations(5)
        if self.repo.degraded:
            state = "DEGRADED"
        elif stats["entities"] or stats["observations"]:
            state = "SYNCED"
        else:
            state = "SYNCED"  # empty but healthy
        return {"state": state, "entities": stats["entities"],
                "relationships": stats["relationships"],
                "observations": stats["observations"],
                "by_type": stats["by_type"],
                "applications": apps,
                "recent": [f"{o.source}:{o.entity_name}" for o in recent],
                "path": stats["path"], "degraded": stats["degraded"]}

    def health(self) -> Dict[str, Any]:
        snap = self.snapshot()
        return {"state": snap["state"], "available": not snap["degraded"],
                **{k: v for k, v in snap.items() if k != "state"}}
