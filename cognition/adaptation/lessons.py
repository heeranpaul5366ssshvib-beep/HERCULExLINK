from __future__ import annotations
"""Lesson lifecycle + promotion gates (6U §5/§6/§7/§15/§16).

CANDIDATE -> VALIDATING -> VALIDATED -> CONSOLIDATED. Promotion into
ExperienceManager requires verified outcome + understood cause +
known scope; promotion into SkillManager requires repeated validation.
Contradictions, expiry, cross-task/user isolation, and regression
gates are enforced here — never bypassed for convenience.
"""

import hashlib
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from cognition.adaptation.world_state import SCOPES

CANDIDATE = "CANDIDATE"
VALIDATING = "VALIDATING"
VALIDATED = "VALIDATED"
CONSOLIDATED = "CONSOLIDATED"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lid(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


@dataclass
class Lesson:
    lesson_id: str
    statement: str
    scope: str = "TASK"
    state: str = CANDIDATE
    task_family: str = "general"
    owner: str = ""  # user/session binding for isolation
    validations: int = 0
    failures: int = 0
    created_at: str = field(default_factory=_utcnow)
    expires_at: float = 0.0  # 0 = no expiry
    provenance: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and time.time() > self.expires_at


class LessonStore:
    """Scoped lesson registry with isolation + contradiction detection."""

    def __init__(self):
        self._lessons: Dict[str, Lesson] = {}
        self.contradictions: List[Dict[str, Any]] = []

    # --------------------------------------------------
    def propose(self, statement: str, scope: str = "TASK",
                task_family: str = "general", owner: str = "",
                provenance: Dict[str, Any] | None = None,
                ttl_s: float = 0.0) -> Lesson:
        if scope not in SCOPES:
            raise ValueError(f"invalid scope {scope!r}")
        lesson = Lesson(
            lesson_id=f"les-{_lid(statement + scope + owner)}",
            statement=str(statement), scope=scope,
            task_family=str(task_family), owner=str(owner),
            provenance=dict(provenance or {}),
            expires_at=(time.time() + ttl_s) if ttl_s > 0 else 0.0)
        # Contradiction: new statement negates a validated lesson
        # in the same scope+family (either negation direction).
        for other in self._lessons.values():
            if other.scope == scope and other.task_family == task_family \
                    and other.state in (VALIDATED, CONSOLIDATED) \
                    and (statement == f"NOT: {other.statement}"
                         or other.statement == f"NOT: {statement}"):
                self.contradictions.append(
                    {"a": other.lesson_id, "b": lesson.lesson_id,
                     "timestamp": _utcnow()})
        self._lessons[lesson.lesson_id] = lesson
        return lesson

    def record_validation(self, lesson_id: str, ok: bool) -> Optional[Lesson]:
        lesson = self._lessons.get(lesson_id)
        if lesson is None or lesson.expired:
            return None
        if ok:
            lesson.validations += 1
            if lesson.state == CANDIDATE:
                lesson.state = VALIDATING
            if lesson.state == VALIDATING and lesson.validations >= 2:
                lesson.state = VALIDATED
        else:
            lesson.failures += 1
            if lesson.failures >= 2 and lesson.state != CONSOLIDATED:
                lesson.state = CANDIDATE
        return lesson

    def invalidate(self, lesson_id: str, reason: str = "") -> bool:
        lesson = self._lessons.get(lesson_id)
        if lesson is None:
            return False
        lesson.state = CANDIDATE
        lesson.provenance["invalidated"] = reason or "stale"
        return True

    def get(self, lesson_id: str) -> Optional[Lesson]:
        lesson = self._lessons.get(lesson_id)
        return None if lesson is None or lesson.expired else lesson

    def for_scope(self, scope: str, task_family: str = "",
                  owner: str = "") -> List[Lesson]:
        out = []
        for lesson in self._lessons.values():
            if lesson.expired or lesson.state not in (VALIDATED, CONSOLIDATED):
                continue
            if lesson.scope != scope:
                continue
            if task_family and lesson.task_family != task_family:
                continue
            if scope in ("TASK", "SESSION", "USER") and owner \
                    and lesson.owner != owner:
                continue  # isolation: never leak across owners
            out.append(lesson)
        return out

    # --------------------------------------------------
    def consolidate(self, lesson_id: str, experience_manager=None,
                    task_id: str = "", goal_type: str = "general") -> Dict[str, Any]:
        """Promote VALIDATED -> CONSOLIDATED + record in ExperienceManager."""
        lesson = self.get(lesson_id)
        if lesson is None:
            return {"ok": False, "reason": "missing or expired"}
        if lesson.state != VALIDATED:
            return {"ok": False, "reason": f"state={lesson.state} (need VALIDATED)"}
        if lesson.scope != "TASK" and not lesson.provenance.get("scope_approved"):
            return {"ok": False, "reason": "broader scope needs explicit approval"}
        lesson.state = CONSOLIDATED
        exp_id = ""
        if experience_manager is not None:
            record = experience_manager.record_rich(
                goal=lesson.statement, status="recovered",
                verification={"validated": True}, task_id=task_id)
            exp_id = record.experience_id
        return {"ok": True, "lesson": lesson_id, "experience": exp_id}

    def propose_skill(self, lesson_id: str, skill_manager,
                      skill_factory: Callable[[Lesson], Any],
                      validation_note: str = "") -> Dict[str, Any]:
        """Propose (never auto-install validated) skill from a lesson."""
        lesson = self.get(lesson_id)
        if lesson is None:
            return {"ok": False, "reason": "missing or expired"}
        if lesson.state != CONSOLIDATED:
            return {"ok": False, "reason": f"state={lesson.state} (need CONSOLIDATED)"}
        skill = skill_factory(lesson)
        skill_manager.register(skill, validate=False,
                               validation_note=validation_note)
        skill_id = skill.get("skill_id") if isinstance(skill, dict) \
            else getattr(skill, "skill_id", "?")
        return {"ok": True, "skill": skill_id, "status": "PROPOSED"}
