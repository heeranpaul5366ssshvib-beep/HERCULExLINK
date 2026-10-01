from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Goal Manager
Author: Heeran Paul
License: MIT
--------------------------------------------

Goal lifecycle: queued -> active -> completed | failed | cancelled.
Supports priorities, dependencies, and interruption (pause/resume)
without corrupting task state. Legacy helpers (add_goal,
complete_goal, active_goals, completed_goals, clear) keep working.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class GoalManager:

    """
    Manages AI goals.
    """

    VALID = ("QUEUED", "ACTIVE", "PAUSED", "COMPLETED", "FAILED", "CANCELLED")

    def __init__(self):

        self.goals: List[Dict[str, Any]] = []
        self._seq = 0

    ##################################################
    # Lifecycle API
    ##################################################

    def add(self, goal: str, priority: int = 0,
            dependencies: Optional[List[str]] = None,
            metadata: Optional[Dict[str, Any]] = None,
            parent_goal_id: Optional[str] = None,
            deadline: Optional[str] = None) -> str:
        """Queue a goal; returns its id.

        UAI §10: ``parent_goal_id`` links subgoals to their parent and
        ``deadline`` (ISO-8601 string) records a due time when provided.
        Both are additive and default to absent.
        """
        self._seq += 1
        goal_id = f"goal-{self._seq}"
        record: Dict[str, Any] = {
            "id": goal_id,
            "goal": str(goal),
            "status": "QUEUED",
            "priority": int(priority),
            "dependencies": list(dependencies or []),
            "metadata": dict(metadata or {}),
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
        }
        if parent_goal_id:
            record["parent_goal_id"] = str(parent_goal_id)
        if deadline:
            record["deadline"] = str(deadline)
        self.goals.append(record)
        return goal_id

    def subgoals(self, parent_goal_id: str) -> List[Dict[str, Any]]:
        """Direct children of a parent goal (UAI §10 hierarchy view)."""
        return [g for g in self.goals if g.get("parent_goal_id") == parent_goal_id]

    def activate(self, goal_id: str) -> bool:
        return self._move(goal_id, "ACTIVE", from_states=("QUEUED", "PAUSED"))

    def pause(self, goal_id: str) -> bool:
        return self._move(goal_id, "PAUSED", from_states=("QUEUED", "ACTIVE"))

    def complete(self, goal_id: str) -> bool:
        return self._move(goal_id, "COMPLETED", from_states=("QUEUED", "ACTIVE", "PAUSED"))

    def fail(self, goal_id: str, error: str = "") -> bool:
        goal = self._find(goal_id)
        if goal is None or goal["status"] in ("COMPLETED", "CANCELLED"):
            return False
        goal["status"] = "FAILED"
        goal["updated_at"] = _utcnow()
        if error:
            goal["metadata"]["error"] = str(error)[:300]
        return True

    def cancel(self, goal_id: str) -> bool:
        return self._move(goal_id, "CANCELLED",
                          from_states=("QUEUED", "ACTIVE", "PAUSED", "FAILED"))

    def dependencies_met(self, goal_id: str) -> bool:
        goal = self._find(goal_id)
        if goal is None:
            return False
        done = {g["id"] for g in self.goals if g["status"] == "COMPLETED"}
        done |= {g["goal"] for g in self.goals if g["status"] == "COMPLETED"}
        return all(d in done for d in goal["dependencies"])

    def queued_goals(self):
        return [g for g in sorted(self.goals, key=lambda g: (-g["priority"], g["id"]))
                if g["status"] == "QUEUED"]

    def failed_goals(self):
        return [g for g in self.goals if g["status"] == "FAILED"]

    def cancelled_goals(self):
        return [g for g in self.goals if g["status"] == "CANCELLED"]

    def get(self, goal_id: str):
        return self._find(goal_id)

    ##################################################
    # Internals
    ##################################################

    def _find(self, goal_id: str):
        for goal in self.goals:
            if goal.get("id") == goal_id:
                return goal
        return None

    def _move(self, goal_id: str, status: str, from_states) -> bool:
        goal = self._find(goal_id)
        if goal is None or goal["status"] not in from_states:
            return False
        goal["status"] = status
        goal["updated_at"] = _utcnow()
        return True

    ##################################################
    # Legacy helpers (backwards compatible)
    ##################################################

    def add_goal(

        self,

        goal,

    ):

        self.add(goal)
        self.goals[-1]["status"] = "ACTIVE"

    ##################################################

    def complete_goal(

        self,

        index,

    ):

        if 0 <= index < len(self.goals):
            self.goals[index]["status"] = "COMPLETED"
            self.goals[index]["updated_at"] = _utcnow()
            # Legacy shape compatibility.
            self.goals[index]["completed"] = True

    ##################################################

    def active_goals(self):

        return [

            goal

            for goal in self.goals

            if goal.get("status", "ACTIVE") in ("QUEUED", "ACTIVE", "PAUSED")

        ]

    ##################################################

    def completed_goals(self):

        return [

            goal

            for goal in self.goals

            if goal.get("completed", False) or goal.get("status") == "COMPLETED"

        ]

    ##################################################

    def clear(self):

        self.goals.clear()
