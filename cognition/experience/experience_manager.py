from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Experience Manager
Author: Heeran Paul
License: MIT
--------------------------------------------

EXPERIENCE = information about previously attempted tasks: goals,
strategies, tools, outcomes, failures, recovery, verification.

Ownership boundaries (Phase F):

* KNOWLEDGE  (knowledge/)  — world/reference material + provenance.
* MEMORY     (memory/)     — authorized interaction/context retention.
* EXPERIENCE (this module) — reusable task outcomes distilled from the
  durable TaskManager history. Raw execution logs are NOT stored
  verbatim; only distilled, queryable records.

The manager is a read-only observer of TaskManager dicts (no writes
into the task lifecycle) and emits candidate procedures only after
validation (repeated success), never from a single anecdote.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Experience:
    """Distilled record of one completed (or failed) task attempt."""

    experience_id: str
    goal_type: str
    description: str = ""
    strategy: str = ""
    tools_used: List[str] = field(default_factory=list)
    outcome: str = "unknown"
    success: float = 0.0  # 0.0..1.0
    failures: List[str] = field(default_factory=list)
    recovery: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    retries: int = 0
    task_id: str = ""
    recorded_at: str = field(default_factory=_utc_now_iso)
    # Stage 5: rich execution detail (concise summaries, never CoT).
    capabilities: List[str] = field(default_factory=list)
    abilities: List[str] = field(default_factory=list)
    failure_reason: str = ""
    recovery_result: str = ""
    lesson: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "goal_type": self.goal_type,
            "description": self.description,
            "strategy": self.strategy,
            "tools_used": list(self.tools_used),
            "outcome": self.outcome,
            "success": self.success,
            "failures": list(self.failures),
            "recovery": dict(self.recovery),
            "verification": dict(self.verification),
            "retries": self.retries,
            "task_id": self.task_id,
            "recorded_at": self.recorded_at,
            "capabilities": list(self.capabilities),
            "abilities": list(self.abilities),
            "failure_reason": self.failure_reason,
            "recovery_result": self.recovery_result,
            "lesson": self.lesson,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Experience":
        known = set(cls.__dataclass_fields__)
        clean = {k: v for k, v in dict(data or {}).items() if k in known}
        try:
            return cls(experience_id=str(clean.pop("experience_id", "")),
                       goal_type=str(clean.pop("goal_type", "general")), **clean)
        except Exception:
            return cls(experience_id="exp-?", goal_type="general")


@dataclass
class ProcedureProposal:
    """Candidate validated workflow promoted from repeated experience."""

    procedure_id: str
    goal_type: str
    steps: List[str] = field(default_factory=list)
    supporting_experiences: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    validated: bool = False
    validation_note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "procedure_id": self.procedure_id,
            "goal_type": self.goal_type,
            "steps": list(self.steps),
            "supporting_experiences": list(self.supporting_experiences),
            "success_rate": self.success_rate,
            "validated": self.validated,
            "validation_note": self.validation_note,
        }


def _goal_type_of(task: Dict[str, Any]) -> str:
    text = str(task.get("goal") or task.get("description") or "").lower()
    for keyword, label in (
        ("diagnos", "diagnosis"),
        ("repair", "repair"),
        ("rout", "routing"),
        ("plan", "planning"),
        ("research", "research"),
        ("test", "testing"),
        ("migrat", "migration"),
        ("benchmark", "benchmarking"),
    ):
        if keyword in text:
            return label
    return "general"


class ExperienceManager:
    """Distill, store, and query task experiences; propose procedures."""

    def __init__(self, min_samples_for_procedure: int = 3, min_success_for_procedure: float = 0.8):
        self._records: Dict[str, Experience] = {}
        self._procedures: Dict[str, ProcedureProposal] = {}
        self.min_samples_for_procedure = min_samples_for_procedure
        self.min_success_for_procedure = min_success_for_procedure
        # Bound store path (UAI Phase M.1): remembered at load()/bind()
        # time so save() never re-resolves ambient configuration lazily.
        # An unbound manager must be given an explicit path.
        self._store_path: str = ""

    # --------------------------------------------------
    def record_from_task(self, task: Dict[str, Any]) -> Experience:
        """Distill one TaskManager task dict into an Experience record."""
        task_id = str(task.get("id", f"task-{len(self._records) + 1}"))
        status = str(task.get("status", "")).upper()
        history = task.get("history") or []
        errors = [str(e) for e in (task.get("errors") or [])]
        verification = task.get("verification") or {}
        completed = status == "COMPLETED"
        verified = bool(verification.get("verified")) or completed
        success = 1.0 if (completed and verified) else (0.5 if completed else 0.0)
        tools: List[str] = []
        selected_tool = task.get("selected_tool")
        if selected_tool:
            tools.append(str(selected_tool))
        for checkpoint in task.get("checkpoints") or []:
            payload = (checkpoint or {}).get("payload") or {}
            tool = payload.get("tool") or payload.get("step")
            if tool and str(tool) not in tools:
                tools.append(str(tool))
        record = Experience(
            experience_id=f"exp-{len(self._records) + 1}",
            goal_type=_goal_type_of(task),
            description=str(task.get("description") or task.get("goal") or ""),
            strategy=str((task.get("plan") or ["direct"])[0] if task.get("plan") else "direct"),
            tools_used=tools,
            outcome=status.lower(),
            success=success,
            failures=errors,
            recovery=dict(task.get("recovery_decision") or {}),
            verification={"state": task.get("verification_state"), **verification} if verification else {"state": task.get("verification_state")},
            retries=int(task.get("retry_count", 0) or 0),
            task_id=task_id,
        )
        self._records[record.experience_id] = record
        return record

    # --------------------------------------------------
    def record_rich(self, goal: str, capabilities: Optional[List[str]] = None,
                    abilities: Optional[List[str]] = None,
                    verification: Optional[Dict[str, Any]] = None,
                    failure_reason: str = "", replans: int = 0,
                    status: str = "failed", task_id: str = "",
                    correlation_id: str = "") -> Experience:
        """Record a Stage-5 rich experience (outcome + lesson, no CoT).

        Outcomes: SUCCESS (completed, no replan), RECOVERED (completed
        after replan), PARTIAL, FAILED (no replan), UNRECOVERED (replans
        exhausted). Lessons are deterministic one-line templates.
        """
        status = str(status or "failed").lower()
        replans = int(replans or 0)
        capabilities = [str(c).upper() for c in (capabilities or [])]
        abilities = [str(a) for a in (abilities or [])]
        if status == "completed":
            outcome = "RECOVERED" if replans > 0 else "SUCCESS"
            success = 1.0
        elif status == "partial":
            outcome, success = "PARTIAL", 0.5
        else:
            outcome = "UNRECOVERED" if replans > 0 else "FAILED"
            success = 0.0
        verified = int((verification or {}).get("passed_steps", 0) or 0)
        if outcome in ("SUCCESS", "RECOVERED"):
            lesson = (f"{' → '.join(abilities) or 'pipeline'} succeeded for "
                      f"{'/'.join(capabilities) or 'goal'} ({verified} verified)")
        elif outcome == "PARTIAL":
            lesson = (f"partial progress for {'/'.join(capabilities)}; "
                      f"retry remainder, not completed steps")
        else:
            lesson = (f"{'/'.join(abilities) or 'no ability'} failed for "
                      f"{'/'.join(capabilities) or 'goal'}: "
                      f"{failure_reason[:160] or 'unverified outcome'}")
        record = Experience(
            experience_id=f"exp-{len(self._records) + 1}",
            goal_type=_goal_type_of({"goal": goal}),
            description=str(goal)[:300],
            strategy="autonomous-loop",
            tools_used=list(abilities),
            outcome=outcome, success=success,
            failures=[failure_reason[:300]] if failure_reason and success < 1.0 else [],
            recovery={"replans": replans,
                      "result": "recovered" if outcome == "RECOVERED" else (
                          "exhausted" if outcome == "UNRECOVERED" else "none")},
            verification=dict(verification or {}),
            retries=replans, task_id=task_id,
            capabilities=capabilities, abilities=abilities,
            failure_reason=failure_reason[:300],
            recovery_result=str(correlation_id)[:64],
            lesson=lesson[:300],
        )
        self._records[record.experience_id] = record
        return record

    _WORD_RE = None

    def find_relevant(self, goal: str, limit: int = 5,
                      outcome: str = "") -> List[Experience]:
        """Deterministic retrieval: token overlap + success ordering."""
        import re as _re
        query = set(_re.findall(r"[a-z0-9]+", str(goal or "").lower()))
        if not query:
            return []
        scored = []
        for record in self._records.values():
            if outcome and record.outcome != outcome.upper():
                continue
            haystack = set(_re.findall(
                r"[a-z0-9]+",
                f"{record.description} {' '.join(record.capabilities)} "
                f"{' '.join(record.abilities)} {record.lesson}".lower()))
            overlap = query & haystack
            if not overlap:
                continue
            score = len(overlap) / max(1, len(query)) * 0.7 + record.success * 0.3
            scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].recorded_at), reverse=True)
        return [record for _, record in scored[: max(0, limit)]]

    # --------------------------------------------------
    # Persistence (Stage 5: experiences survive restarts)
    # --------------------------------------------------
    def bind(self, path: str) -> str:
        """Bind the store path for subsequent save() calls (no I/O)."""
        self._store_path = str(path or "")
        return self._store_path

    @property
    def store_path(self) -> str:
        """Currently bound store path ("" when unbound)."""
        return self._store_path

    def save(self, path: str = "") -> bool:
        import json as _json
        import tempfile as _tempfile
        from pathlib import Path as _Path
        target_arg = str(path or "") or self._store_path
        if not target_arg:
            import logging as _logging
            _logging.getLogger("HERCULE.Experience").warning(
                "experience save refused: no bound store path (bind() or pass path)")
            return False
        try:
            from system.state_guard import check_state_write

            target_arg = check_state_write(target_arg, owner="experience")
        except Exception as exc:
            import logging as _logging
            _logging.getLogger("HERCULE.Experience").warning(
                "experience save blocked: %s", exc)
            return False
        try:
            target = _Path(target_arg)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1,
                       "records": [r.as_dict() for r in self._records.values()]}
            fd, tmp = _tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
            try:
                with open(fd, "w", encoding="utf-8") as handle:
                    _json.dump(payload, handle, ensure_ascii=False, indent=1)
                _Path(tmp).replace(target)
            except Exception:
                try:
                    _Path(tmp).unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            return True
        except Exception as exc:
            import logging as _logging
            _logging.getLogger("HERCULE.Experience").warning("experience save failed: %s", exc)
            return False

    def load(self, path: str) -> int:
        import json as _json
        from pathlib import Path as _Path
        self._records.clear()
        self._store_path = str(path or "")
        target = _Path(path)
        if not target.exists():
            return 0
        try:
            data = _json.loads(target.read_text(encoding="utf-8"))
        except Exception as exc:
            backup = target.with_suffix(".corrupt.bak")
            try:
                target.replace(backup)
            except Exception:
                pass
            import logging as _logging
            _logging.getLogger("HERCULE.Experience").warning(
                "experience store corrupt (%s); backed up, starting empty", exc)
            return 0
        loaded = 0
        items = data.get("records", []) if isinstance(data, dict) else []
        for item in items:
            try:
                record = Experience.from_dict(item)
                self._records[record.experience_id] = record
                loaded += 1
            except Exception:
                continue
        return loaded

    # --------------------------------------------------
    def query(self, goal_type: Optional[str] = None, min_success: float = 0.0, limit: int = 10) -> List[Experience]:
        results = [
            record
            for record in self._records.values()
            if (goal_type is None or record.goal_type == goal_type) and record.success >= min_success
        ]
        results.sort(key=lambda r: (r.success, r.recorded_at), reverse=True)
        return results[: max(0, limit)]

    def history_for_goal(self, goal_type: str) -> List[Experience]:
        return self.query(goal_type=goal_type, limit=1000)

    # --------------------------------------------------
    def propose_procedure(self, goal_type: str) -> Optional[ProcedureProposal]:
        """Promote repeated successful experience to a candidate procedure.

        Requires ``min_samples_for_procedure`` experiences with mean
        success >= ``min_success_for_procedure``; otherwise returns None
        (no promotion from anecdotes).
        """
        group = [r for r in self._records.values() if r.goal_type == goal_type and r.success >= 0.5]
        if len(group) < self.min_samples_for_procedure:
            return None
        mean_success = sum(r.success for r in group) / len(group)
        if mean_success < self.min_success_for_procedure:
            return None
        # Most common strategy + union of tools, ordered by frequency.
        strategies: Dict[str, int] = defaultdict(int)
        tool_votes: Dict[str, int] = defaultdict(int)
        for record in group:
            strategies[record.strategy] += 1
            for tool in record.tools_used:
                tool_votes[tool] += 1
        best_strategy = max(strategies, key=strategies.get)
        steps = [f"strategy: {best_strategy}"] + [f"use {tool}" for tool, _ in sorted(tool_votes.items(), key=lambda kv: kv[1], reverse=True)]
        proposal = ProcedureProposal(
            procedure_id=f"proc-{goal_type}-{len(self._procedures) + 1}",
            goal_type=goal_type,
            steps=steps,
            supporting_experiences=[r.experience_id for r in group],
            success_rate=round(mean_success, 3),
            validated=False,
            validation_note=f"{len(group)} supporting experiences, mean success {mean_success:.2f}; needs human/tool approval",
        )
        self._procedures[proposal.procedure_id] = proposal
        return proposal

    def validate_procedure(self, procedure_id: str, approved: bool, note: str = "") -> Optional[ProcedureProposal]:
        proposal = self._procedures.get(procedure_id)
        if proposal is None:
            return None
        proposal.validated = bool(approved)
        if note:
            proposal.validation_note = note
        return proposal

    # --------------------------------------------------
    def statistics(self) -> Dict[str, Any]:
        by_goal: Dict[str, int] = defaultdict(int)
        for record in self._records.values():
            by_goal[record.goal_type] += 1
        return {
            "experiences": len(self._records),
            "procedures": len(self._procedures),
            "validated_procedures": sum(1 for p in self._procedures.values() if p.validated),
            "by_goal_type": dict(by_goal),
        }
