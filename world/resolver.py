from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Resolver (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured questions over world state. Every answer carries
evidence/source metadata; unknown questions say so honestly instead
of guessing. Live TaskManager state is consulted by reference for
task questions (the world model never overrides task authority).
"""

import re
from typing import Any, Dict, List, Optional

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class WorldResolver:
    """Evidence-tagged answers from a WorldModel (+ optional tasks)."""

    def __init__(self, world, task_manager=None):
        self.world = world
        self.tasks = task_manager

    # --------------------------------------------------
    def answer(self, question: str) -> Dict[str, Any]:
        lowered = str(question or "").lower()
        if any(k in lowered for k in ("running", "open application", "what application")):
            return self.running_applications()
        if "where is" in lowered or ("where" in lowered and "file" in lowered):
            return self.file_location(_topic(question))
        if "contain" in lowered and "project" in lowered:
            return self.project_contents(_topic(question))
        if "active" in lowered and "task" in lowered:
            return self.active_task()
        if "device" in lowered:
            return self.known_devices()
        if "visible" in lowered or "object" in lowered:
            return self.visible_objects()
        if "changed" in lowered or "recent" in lowered:
            return self.recent_changes()
        if "goal" in lowered:
            return self.current_goals()
        return {"status": "unknown",
                "answer": "I don't have verified world state for that question.",
                "evidence": []}

    # --------------------------------------------------
    def running_applications(self) -> Dict[str, Any]:
        repo = self.world.repo
        apps = [e for e in repo.entities.values()
                if e.type == "application" and not e.stale
                and str(e.properties.get("state", "")).lower() == "running"]
        evidence = [{"entity": e.id, "source": e.source,
                     "status": e.status, "verified": e.last_verified > 0}
                    for e in apps]
        if not apps:
            return {"status": "empty",
                    "answer": "No running applications in verified world state.",
                    "evidence": []}
        names = ", ".join(sorted(e.name for e in apps))
        return {"status": "answered",
                "answer": f"Running: {names}.",
                "evidence": evidence, "entities": [e.id for e in apps]}

    def file_location(self, topic: str) -> Dict[str, Any]:
        repo = self.world.repo
        matches = [e for e in repo.entities.values()
                   if e.type == "file" and not e.stale
                   and _matches(e, topic)]
        if not matches:
            return {"status": "unknown",
                    "answer": f"I have no verified location for {topic!r}.",
                    "evidence": []}
        best = sorted(matches, key=lambda e: (e.confidence, e.updated_at),
                      reverse=True)[0]
        path = best.properties.get("path", best.name)
        return {"status": "answered",
                "answer": f"{best.name} is at {path}.",
                "evidence": [{"entity": best.id, "source": best.source,
                              "status": best.status,
                              "verified": best.last_verified > 0}],
                "entities": [best.id]}

    def project_contents(self, topic: str) -> Dict[str, Any]:
        repo = self.world.repo
        projects = [e for e in repo.entities.values()
                    if e.type == "project" and not e.stale and _matches(e, topic)]
        if not projects:
            return {"status": "unknown",
                    "answer": f"I know no project matching {topic!r}.",
                    "evidence": []}
        project = projects[0]
        members = [r.target_id for r in repo.relationships.values()
                   if r.source_id == project.id and r.relation == "contains"]
        names = [repo.entities[m].name for m in members if m in repo.entities]
        detail = f" ({', '.join(names)})" if names else " (no files recorded)"
        return {"status": "answered",
                "answer": f"Project {project.name} contains{detail}.",
                "evidence": [{"entity": project.id, "source": project.source,
                              "status": project.status}],
                "entities": [project.id] + members}

    def active_task(self) -> Dict[str, Any]:
        if self.tasks is not None:
            try:
                current = None
                if hasattr(self.tasks, "current_task"):
                    current = self.tasks.current_task()
                elif hasattr(self.tasks, "active_tasks"):
                    actives = self.tasks.active_tasks() or []
                    current = actives[0] if actives else None
                if isinstance(current, dict) and current:
                    goal = current.get("goal", current.get("id", "unknown"))
                    return {"status": "answered",
                            "answer": f"Active task: {goal} "
                                      f"({current.get('status', 'active')}).",
                            "evidence": [{"source": "task-manager",
                                          "status": current.get("status", "")}],
                            "task_id": current.get("id", "")}
            except Exception:
                pass
        repo = self.world.repo
        actives = [e for e in repo.entities.values()
                   if e.type == "task" and not e.stale
                   and str(e.properties.get("status", "")).lower() in ("active", "running")]
        if not actives:
            return {"status": "empty",
                    "answer": "No active task recorded.",
                    "evidence": []}
        names = ", ".join(e.name for e in actives)
        return {"status": "answered", "answer": f"Active task: {names}.",
                "evidence": [{"entity": e.id, "source": e.source} for e in actives]}

    def known_devices(self) -> Dict[str, Any]:
        repo = self.world.repo
        devices = [e for e in repo.entities.values()
                   if e.type == "device" and not e.stale]
        if not devices:
            return {"status": "empty",
                    "answer": "No devices recorded.",
                    "evidence": []}
        return {"status": "answered",
                "answer": "Known devices: " + ", ".join(e.name for e in devices) + ".",
                "evidence": [{"entity": e.id, "source": e.source} for e in devices]}

    def visible_objects(self) -> Dict[str, Any]:
        repo = self.world.repo
        objects = [e for e in repo.entities.values()
                   if e.type == "object" and not e.stale]
        if not objects:
            return {"status": "empty",
                    "answer": "No visible objects recorded.",
                    "evidence": []}
        return {"status": "answered",
                "answer": "Visible: " + ", ".join(e.name for e in objects) + ".",
                "evidence": [{"entity": e.id, "source": e.source} for e in objects]}

    def recent_changes(self, limit: int = 5) -> Dict[str, Any]:
        recent = self.world.repo.recent_observations(limit)
        if not recent:
            return {"status": "empty",
                    "answer": "No recent world observations.",
                    "evidence": []}
        items = [f"{o.source}:{o.entity_name}" for o in recent]
        return {"status": "answered",
                "answer": "Recent: " + "; ".join(items) + ".",
                "evidence": [{"observation": o.id, "source": o.source,
                              "status": o.status} for o in recent]}

    def current_goals(self) -> Dict[str, Any]:
        repo = self.world.repo
        goals = [e for e in repo.entities.values()
                 if e.type == "goal" and not e.stale]
        if not goals:
            return {"status": "empty",
                    "answer": "No goals recorded.",
                    "evidence": []}
        return {"status": "answered",
                "answer": "Goals: " + "; ".join(e.name for e in goals) + ".",
                "evidence": [{"entity": e.id, "source": e.source} for e in goals]}


def _topic(question: str) -> str:
    match = re.search(r"(?i)(?:where is|contains?)\s+(.+?)[?.]*$", str(question or ""))
    if match:
        return match.group(1).strip().strip("\"'")[:120]
    words = [w for w in _TOKEN_RE.findall(str(question or "").lower())
             if w not in ("what", "where", "which", "the", "a", "an", "is",
                          "are", "currently", "project", "file", "task")]
    return " ".join(words[:6]) or str(question or "")[:120]


def _matches(entity, topic: str) -> bool:
    topic = str(topic or "").lower().strip()
    if not topic:
        return False
    blob = f"{entity.name} {entity.properties.get('path', '')}".lower()
    if topic in blob:
        return True
    return bool(set(_TOKEN_RE.findall(topic)) & set(_TOKEN_RE.findall(blob)))
