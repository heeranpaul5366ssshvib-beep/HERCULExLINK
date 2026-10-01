from __future__ import annotations
"""Adaptive executor (6U core loop + §10 safety + §11 export).

Task -> plan -> act -> verify -> (success: consolidate | failure:
record -> diagnose -> revise (policy-gated) -> retry -> verify) ->
retain validated lesson. Operates THROUGH injected managers; modifies
no weights, code, policy, or permissions. Offline examples export to
the Phase-6 postdata-compatible format for future training use.
"""

import time
from typing import Any, Callable, Dict, List, Optional

from cognition.adaptation import failures as _fail
from cognition.adaptation.diagnosis import diagnose, revision_for
from cognition.adaptation.lessons import LessonStore
from cognition.adaptation.retry import RetryBudget, decide_retry
from cognition.adaptation.world_state import TaskStateLedger


class AdaptiveExecutor:
    """Mistake-driven executor with dependency-injected collaborators."""

    def __init__(self, planner=None, policy=None, memory=None,
                 experience=None, skills=None,
                 max_retries: int = 3, max_seconds: float = 300.0,
                 owner: str = ""):
        self.planner = planner
        self.policy = policy
        self.memory = memory
        self.experience = experience
        self.skills = skills
        self.max_retries = max_retries
        self.max_seconds = max_seconds
        self.owner = owner
        self.lessons = LessonStore()
        self.failures: List[Dict[str, Any]] = []

    # --------------------------------------------------
    def run(self, task_id: str, goal: str,
            act: Callable[[Dict[str, Any]], Dict[str, Any]],
            verify: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
            plan: List[str] | None = None,
            alternatives: List[Dict[str, Any]] | None = None,
            environment: Dict[str, Any] | None = None,
            approver: Optional[Callable[[Dict[str, Any]], bool]] = None,
            autonomy: str = "standard") -> Dict[str, Any]:
        """Execute one task with adaptation. Returns a structured trace."""
        t0 = time.perf_counter()
        ledger = TaskStateLedger(task_id)
        budget = RetryBudget(max_retries=self.max_retries,
                             max_seconds=self.max_seconds)
        steps = list(plan or [goal])
        if self.planner is not None:
            try:
                steps = [s.get("description", str(s)) for s in
                         self.planner.create(goal, list(steps))] or steps
            except Exception:
                pass
        trace: Dict[str, Any] = {"task_id": task_id, "goal": goal,
                                 "attempts": [], "retries": 0,
                                 "recovered": False, "verified": False,
                                 "lesson": None}
        action: Dict[str, Any] = {"step_id": "s1", "action": steps[0] if steps else goal,
                                  "tool": "", "input": {}, "plan": steps}
        outcome = self._attempt(action, act, verify, environment or {})
        trace["attempts"].append(outcome)
        if outcome["verified"]:
            trace["verified"] = True
            self._consolidate_success(task_id, goal, action, outcome)
            trace.update(self._final(trace, t0, "success"))
            return trace
        # ---- failure loop ----
        record = _fail.build_record(task_id, goal, action,
                                    outcome.get("observation", ""),
                                    environment=environment)
        self.failures.append(record.as_dict())
        diagnosis = diagnose(record)
        lesson = self.lessons.propose(
            f"When {record.tool or record.attempted_action} fails with "
            f"{record.failure_type}, try {diagnosis.should_change or 'an alternative'}.",
            scope="TASK", owner=self.owner,
            provenance={"failure": record.as_dict(),
                        "diagnosis": diagnosis.as_dict()})
        while True:
            revised = revision_for(diagnosis, action, alternatives)
            gate = decide_retry(action, {**revised["action"],
                                         "revision_note": revised["reason"]},
                                budget, policy=self.policy,
                                autonomy=autonomy, approver=approver)
            if not gate["allow"]:
                trace["blocked"] = gate["reason"]
                break
            trace["retries"] += 1
            action = {**revised["action"], "step_id": f"s{trace['retries'] + 1}"}
            # World-state update from the failure (provenance intact).
            ledger.update(f"tool:{record.tool or 'action'}",
                          f"rejected: {record.failure_type}",
                          observation=record.observation[:300],
                          source="task-observation",
                          confidence=record.confidence)
            outcome = self._attempt(action, act, verify, environment or {},
                                    new_evidence=True)
            trace["attempts"].append(outcome)
            if outcome["verified"]:
                trace["verified"] = True
                trace["recovered"] = True
                record.final_outcome = "recovered"
                self.lessons.record_validation(lesson.lesson_id, True)
                self.lessons.record_validation(lesson.lesson_id, True)
                consolidated = self.lessons.consolidate(
                    lesson.lesson_id, self.experience,
                    task_id=task_id)
                trace["lesson"] = {"id": lesson.lesson_id,
                                   "statement": lesson.statement,
                                   "consolidated": consolidated.get("ok", False)}
                self._working_note(task_id, lesson.statement)
                break
            # Retry failed too: re-diagnose with the new observation.
            record = _fail.build_record(task_id, goal, action,
                                        outcome.get("observation", ""),
                                        environment=environment)
            self.failures.append(record.as_dict())
            diagnosis = diagnose(record)
            if budget.exhausted:
                trace["blocked"] = "budget exhausted"
                break
        trace.update(self._final(trace, t0,
                                 "recovered" if trace["verified"] else "failed"))
        return trace

    # --------------------------------------------------
    def _attempt(self, action, act, verify, environment, new_evidence=False):
        try:
            result = act(dict(action)) or {}
        except Exception as exc:
            result = {"observation": f"error: {exc}", "ok": False}
        try:
            verdict = verify(dict(action), dict(result)) or {}
        except Exception as exc:
            verdict = {"verified": False, "detail": f"verifier error: {exc}"}
        return {"action": action_signature(action),
                "observation": str(result.get("observation", "")),
                "verified": bool(verdict.get("verified")),
                "detail": str(verdict.get("detail", ""))}

    def _consolidate_success(self, task_id, goal, action, outcome):
        if self.experience is not None:
            try:
                self.experience.record_rich(
                    goal=goal, status="completed",
                    verification={"verified": True}, task_id=task_id)
            except Exception:
                pass

    def _working_note(self, task_id, statement):
        if self.memory is not None:
            try:
                working = getattr(self.memory, "working", None)
                if working is not None and hasattr(working, "add"):
                    working.add({"task": task_id, "lesson": statement})
                elif hasattr(self.memory, "store"):
                    self.memory.store(f"task:{task_id}", statement)
            except Exception:
                pass

    def _final(self, trace, t0, outcome):
        return {"outcome": outcome,
                "wall_s": round(time.perf_counter() - t0, 3),
                "failures": len(self.failures)}


def action_signature(action: Dict[str, Any]) -> str:
    import json

    core = {k: action.get(k) for k in ("tool", "action", "input")}
    return json.dumps(core, sort_keys=True, default=str)
