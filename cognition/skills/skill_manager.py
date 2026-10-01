from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Skill Manager
Author: Heeran Paul
License: MIT
--------------------------------------------

UAI §21/§22 — Skill system and acquisition architecture.

Responsibilities:

* Registry of reusable skills (proposed → validated lifecycle).
* Acquisition gate: unfamiliar tasks must either match an existing
  skill, be solvable by existing registered abilities, or be
  reported as a capability gap. Nothing is auto-installed and
  nothing bypasses the ability/policy path.
* Procedural-experience bridge: validated procedure proposals from
  ExperienceManager can be reviewed into real skills.

Skills never execute anything themselves; they are consumed by the
planner/executor as workflow metadata. All execution still flows
through AbilityManager (permissions, inputs, verification).
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from cognition.skills.skill import (
    SKILL_STATUS_DISABLED,
    SKILL_STATUS_PROPOSED,
    SKILL_STATUS_VALIDATED,
    Skill,
)

logger = logging.getLogger("HERCULE.Skills")

EVENT_SKILL_PROPOSED = "SKILL_PROPOSED"
EVENT_SKILL_REGISTERED = "SKILL_REGISTERED"
EVENT_SKILL_DISABLED = "SKILL_DISABLED"


class SkillManager:
    """Registry + acquisition gate for reusable skills."""

    def __init__(self, ability_manager=None, experience_manager=None,
                 store_path: Optional[Path] = None, event_bus=None):
        self.abilities = ability_manager
        self.experience = experience_manager
        self.event_bus = event_bus
        self._skills: Dict[str, Skill] = {}
        self._lock = threading.RLock()
        self._store_path = Path(store_path) if store_path else None

    # ------------------------------------------------------------------
    # Persistence (data/skills/skills.json or env-overridable)
    # ------------------------------------------------------------------
    def set_store_path(self, path: Path) -> None:
        self._store_path = Path(path)

    def load(self) -> int:
        if self._store_path is None or not self._store_path.exists():
            return 0
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            with self._lock:
                for item in data.get("skills", []):
                    try:
                        skill = Skill.from_dict(item)
                        self._skills[skill.skill_id] = skill
                    except TypeError:
                        continue
            return len(self._skills)
        except Exception as exc:
            logger.warning("skill store unreadable (%s): %s", self._store_path, exc)
            return 0

    def save(self) -> None:
        if self._store_path is None:
            return
        from system.state_guard import check_state_write

        check_state_write(str(self._store_path), owner="skills")
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {"skills": [s.to_dict() for s in self._skills.values()]}
            self._store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("skill store write failed (%s): %s", self._store_path, exc)

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------
    def register(self, skill: Skill, *, validate: bool = False,
                 validation_note: str = "") -> Skill:
        """Register a skill; `validate=True` marks it validated (tested)."""
        if not skill.skill_id or not skill.procedure:
            raise ValueError("skill requires skill_id and a non-empty procedure")
        with self._lock:
            existing = self._skills.get(skill.skill_id)
            if existing is not None and existing is not skill:
                raise ValueError(f"Skill '{skill.skill_id}' is already registered")
            skill.status = SKILL_STATUS_VALIDATED if validate else SKILL_STATUS_PROPOSED
            now = datetime.now(timezone.utc).isoformat()
            skill.updated_at = now
            skill.created_at = skill.created_at or now
            if validate and validation_note:
                skill.provenance["validation_note"] = validation_note
            self._skills[skill.skill_id] = skill
        self._emit(EVENT_SKILL_REGISTERED if validate else EVENT_SKILL_PROPOSED, skill.skill_id)
        self.save()
        return skill

    def get(self, skill_id: str) -> Optional[Skill]:
        with self._lock:
            return self._skills.get(skill_id)

    def list(self, *, status: Optional[str] = None) -> List[Skill]:
        """All skills, optionally filtered by status (read-only view)."""
        with self._lock:
            skills = list(self._skills.values())
        if status is not None:
            skills = [s for s in skills if s.status == status]
        return skills

    def unregister(self, skill_id: str) -> bool:
        """Remove a skill from the registry (returns False when absent)."""
        with self._lock:
            if skill_id not in self._skills:
                return False
            del self._skills[skill_id]
        self.save()
        return True

    def resolve(self, goal: str) -> Optional[Skill]:
        """Best validated skill for a goal, or None (never raises)."""
        matches = self.match(goal)
        return matches[0] if matches else None

    def validate(self, skill_id: str, validation_note: str = "") -> Optional[Skill]:
        """Mark a proposed skill validated after review (None when absent)."""
        from datetime import datetime, timezone as _tz

        with self._lock:
            skill = self._skills.get(skill_id)
            if skill is None:
                return None
            skill.status = SKILL_STATUS_VALIDATED
            skill.updated_at = datetime.now(_tz.utc).isoformat()
            if validation_note:
                skill.provenance["validation_note"] = validation_note
        self._emit(EVENT_SKILL_REGISTERED, skill_id)
        self.save()
        return skill

    def all(self) -> List[Skill]:
        with self._lock:
            return list(self._skills.values())

    def usable(self) -> List[Skill]:
        """Validated skills only — proposed skills are advisory."""
        return [s for s in self.all() if s.is_registered()]

    def disable(self, skill_id: str) -> bool:
        with self._lock:
            skill = self._skills.get(skill_id)
            if skill is None:
                return False
            skill.status = SKILL_STATUS_DISABLED
        self._emit(EVENT_SKILL_DISABLED, skill_id)
        self.save()
        return True

    def match(self, goal: str) -> List[Skill]:
        """Best-first validated skills whose description/procedure overlaps the goal.

        Conservative threshold: at least 2 shared tokens and at least
        half the goal's tokens, so a single common word (e.g.
        "calculate") can never hijack an unrelated goal's plan.
        """
        goal_tokens = [tok for tok in (goal or "").lower().split() if tok]
        if not goal_tokens:
            return []
        minimum = max(2, len(goal_tokens) // 2)
        scored: List[tuple[float, Skill]] = []
        for skill in self.usable():
            hay = " ".join([skill.description] + list(skill.procedure)).lower()
            overlap = sum(1 for tok in goal_tokens if tok and tok in hay)
            if overlap >= minimum:
                scored.append((float(overlap), skill))
        scored.sort(key=lambda pair: (-pair[0], pair[1].skill_id))
        return [s for _, s in scored]

    # ------------------------------------------------------------------
    # Acquisition gate (§22)
    # ------------------------------------------------------------------
    def evaluate_gap(self, task: str, required_capabilities: Optional[List[str]] = None) -> Dict[str, Any]:
        """Classify how an unfamiliar task can be served — never auto-install.

        Returns one of:
          skill_match      — a validated skill covers the task
          ability_coverage — registered abilities cover the required capabilities
          proposal         — a procedural proposal from experience can be reviewed
          capability_gap   — genuinely missing; must be reported honestly
        """
        required = [str(c).upper() for c in (required_capabilities or [])]

        matches = self.match(task)
        if matches:
            return {"resolution": "skill_match", "skill_id": matches[0].skill_id,
                    "candidates": [s.skill_id for s in matches[:3]]}

        missing: List[str] = []
        for cap in required:
            found = False
            if self.abilities is not None:
                try:
                    # Real AbilityManager.lookup_by_capability returns a
                    # list (possibly empty); stubs may return an object
                    # or None. Truthiness — not None-ness — decides.
                    found = bool(self.abilities.lookup_by_capability(cap))
                except Exception:
                    found = False
            if not found:
                missing.append(cap)
        if not missing:
            return {"resolution": "ability_coverage", "covered": required}

        # Advisory: a promoted procedure may exist for this task type.
        if self.experience is not None:
            try:
                proposal = self.experience.propose_procedure(task[:60])
            except Exception:
                proposal = None
            if proposal is not None:
                return {"resolution": "proposal",
                        "proposal": getattr(proposal, "procedure_id", None),
                        "needs_approval": True}

        return {"resolution": "capability_gap", "missing_capabilities": missing,
                "message": f"No registered skill or ability covers: {', '.join(missing)}"}

    # ------------------------------------------------------------------
    # Experience bridge
    # ------------------------------------------------------------------
    def register_from_experience(self, proposal) -> Optional[Skill]:
        """Review a validated ExperienceManager procedure proposal into a skill.

        The proposal must be marked validated by the experience layer;
        HERCULE never self-promotes unvalidated procedures.
        """
        if proposal is None or not getattr(proposal, "validated", False):
            return None
        skill = Skill(
            skill_id=f"skill-{proposal.goal_type[:40]}-{getattr(proposal, 'procedure_id', 'x')}",
            description=f"Learned procedure for '{proposal.goal_type}'",
            procedure=list(getattr(proposal, "steps", [])),
            source="experience",
            provenance={"supporting_experiences": list(getattr(proposal, "supporting_experiences", [])),
                        "success_rate": getattr(proposal, "success_rate", None)},
        )
        return self.register(skill, validate=False)

    # ------------------------------------------------------------------
    def record_outcome(self, skill_id: str, success: bool) -> bool:
        skill = self.get(skill_id)
        if skill is None:
            return False
        skill.record_outcome(success)
        self.save()
        return True

    def stats(self) -> Dict[str, Any]:
        skills = self.all()
        return {
            "total": len(skills),
            "validated": sum(1 for s in skills if s.is_registered()),
            "proposed": sum(1 for s in skills if s.status == SKILL_STATUS_PROPOSED),
            "disabled": sum(1 for s in skills if s.status == SKILL_STATUS_DISABLED),
        }

    # ------------------------------------------------------------------
    def _emit(self, event: str, skill_id: str) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.publish(event, skill_id)
        except Exception:
            pass
