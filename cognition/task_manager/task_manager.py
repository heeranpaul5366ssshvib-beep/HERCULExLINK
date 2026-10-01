from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Task Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from security.permissions.policy_manager import PolicyManager


class TaskStatus(str):
    """Case-insensitive status wrapper for compatibility with legacy task assertions."""

    def __new__(cls, value: str):
        return str.__new__(cls, str(value).upper())

    def __eq__(self, other):
        if isinstance(other, str):
            return str(self).lower() == other.lower()
        return str.__eq__(self, other)

    __hash__ = str.__hash__


class TaskManager:
    """Durable task lifecycle with checkpoints, retries, recovery, verification, and permissions."""

    VALID_STATES = {
        "CREATED": {"QUEUED", "WAITING", "RUNNING", "CANCELLED"},
        "QUEUED": {"PLANNING", "WAITING", "RUNNING", "CANCELLED", "FAILED"},
        "PLANNING": {"WAITING", "RUNNING", "WAITING_FOR_APPROVAL", "PAUSED", "CANCELLED", "FAILED", "RETRYING", "RECOVERING"},
        "WAITING": {"RUNNING", "PAUSED", "WAITING_FOR_APPROVAL", "CANCELLED", "FAILED"},
        "RUNNING": {"PAUSED", "WAITING_FOR_APPROVAL", "VERIFYING", "FAILED", "CANCELLED", "RETRYING", "RECOVERING"},
        "PAUSED": {"RUNNING", "WAITING", "CANCELLED", "FAILED"},
        "WAITING_FOR_APPROVAL": {"RUNNING", "FAILED", "CANCELLED", "RETRYING"},
        "RETRYING": {"RUNNING", "WAITING", "VERIFYING", "FAILED", "RECOVERING", "COMPLETED"},
        "VERIFYING": {"COMPLETED", "FAILED", "RUNNING"},
        "COMPLETED": set(),
        "FAILED": {"RETRYING", "RECOVERING", "CANCELLED"},
        "CANCELLED": set(),
        "RECOVERING": {"RUNNING", "WAITING", "FAILED", "CANCELLED"},
    }

    def __init__(self, storage_path: Optional[str] = None, policy: Optional[PolicyManager] = None, event_bus=None):
        self.storage_path = storage_path
        self.policy = policy or PolicyManager()
        self.event_bus = event_bus
        self.tasks: list[dict[str, Any]] = []
        self._tasks_by_id: Dict[str, Dict[str, Any]] = {}
        self._queue: list[str] = []
        self._load()

    def _utcnow(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _normalize_status(self, status: str) -> str:
        return str(status).upper()

    def _emit(self, event_name: str, task_id: str, **metadata: Any):
        if self.event_bus is None:
            return
        payload = {"task_id": task_id, "timestamp": self._utcnow(), "source": "TaskManager"}
        payload.update(metadata)
        try:
            self.event_bus.publish(event_name, payload)
        except Exception:
            pass  # observability never breaks task transitions

    def _persist(self):
        if not self.storage_path:
            return
        # UAI Phase M.1: fail closed under test isolation instead of
        # silently persisting outside the evaluation state dir.
        from system.state_guard import check_state_write

        check_state_write(str(self.storage_path), owner="tasks")
        path = Path(self.storage_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tasks": list(self._tasks_by_id.values())}
        # Atomic write: a crash mid-write must never leave a truncated
        # store behind (readers tolerate corruption, but we avoid it).
        tmp_path = path.with_name(path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, default=str)
        os.replace(tmp_path, path)

    def _load(self):
        if not self.storage_path:
            return
        path = Path(self.storage_path)
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return
        tasks = payload.get("tasks", []) if isinstance(payload, dict) else []
        if not isinstance(tasks, list):
            return
        for task in tasks:
            # Skip malformed entries individually: one bad record must
            # never prevent the remaining durable tasks from loading.
            if not isinstance(task, dict) or not task.get("id"):
                continue
            task_id = str(task["id"])
            task["status"] = TaskStatus(task.get("status", "CREATED"))
            self._tasks_by_id[task_id] = task
            self.tasks.append({"id": task_id, "task": task.get("description") or task.get("goal"), "completed": task.get("status") == "COMPLETED", "status": TaskStatus(task.get("status", "CREATED"))})
            if task_id not in self._queue:
                self._queue.append(task_id)

    def create_task(
        self,
        description: str,
        timeout: int = 60,
        metadata: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        goal: Optional[str] = None,
        plan: Optional[Iterable[str]] = None,
        dependencies: Optional[Iterable[str]] = None,
        priority: int = 5,
        parent_task_id: Optional[str] = None,
        required_permissions: Optional[Iterable[str]] = None,
        expected_result: Any = None,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> str:
        task_key = task_id or f"task-{len(self._tasks_by_id) + 1}"
        task = {
            "id": task_key,
            "description": description,
            "goal": goal or description,
            "status": TaskStatus("CREATED"),
            "timeout": timeout,
            "retries": 0,
            "retry_count": 0,
            "max_retries": 2,
            "priority": priority,
            "parent_task_id": parent_task_id,
            "dependencies": list(dependencies or []),
            "plan": list(plan or []),
            "current_step": None,
            "completed_steps": [],
            "pending_steps": list(plan or []),
            "failed_steps": [],
            "checkpoints": [],
            "history": [],
            "outputs": [],
            "errors": [],
            "verification_state": "PENDING",
            "required_permissions": list(required_permissions or []),
            "expected_result": expected_result,
            "selected_model": model,
            "selected_agent": agent,
            "selected_tool": tool,
            "created_at": self._utcnow(),
            "updated_at": self._utcnow(),
            "started_at": None,
            "completed_at": None,
            "cancelled_at": None,
            "paused_at": None,
            "last_error": None,
            "result": None,
            "metadata": dict(metadata or {}),
            "verification": None,
            "recovery_decision": None,
        }
        self._tasks_by_id[task_key] = task
        self.tasks.append({"id": task_key, "task": description, "completed": False, "status": TaskStatus("CREATED")})
        task["history"].append({"status": "CREATED", "time": self._utcnow()})
        self._emit("TaskCreated", task_key, goal=task["goal"], timeout=timeout)
        self._persist()
        return task_key

    def get(self, task_id: str) -> Dict[str, Any]:
        return self._tasks_by_id[task_id]

    def add(self, task: str):
        return self.create_task(task)

    def transition(self, task_id: str, new_state: str, *, reason: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        task = self._tasks_by_id[task_id]
        current = str(task.get("status", "CREATED")).upper()
        target = self._normalize_status(new_state)
        allowed = self.VALID_STATES.get(current, set())
        if target not in allowed and current != target:
            raise ValueError(f"Invalid task transition: {current} -> {target}")
        task["status"] = TaskStatus(target)
        task["updated_at"] = self._utcnow()
        if reason:
            task["last_error"] = reason
        task["history"].append({"status": target, "time": self._utcnow(), "reason": reason, "metadata": metadata or {}})
        if target == "RUNNING":
            task["started_at"] = task.get("started_at") or self._utcnow()
        elif target == "COMPLETED":
            task["completed_at"] = self._utcnow()
        elif target == "CANCELLED":
            task["cancelled_at"] = self._utcnow()
        elif target == "PAUSED":
            task["paused_at"] = self._utcnow()
        self._sync_legacy_state(task)
        self._persist()
        return task

    def _validate_dependencies(self, task: Dict[str, Any]):
        for dependency_id in task.get("dependencies", []):
            dep = self._tasks_by_id.get(str(dependency_id))
            if dep is None:
                raise ValueError(f"Task dependency {dependency_id} is missing.")
            if str(dep.get("status", "")).upper() != "COMPLETED":
                raise RuntimeError(f"Dependency {dependency_id} is not completed.")

    def _validate_permissions(self, task: Dict[str, Any]):
        for permission in task.get("required_permissions", []):
            decision = self.policy.evaluate(str(permission).upper(), {"risk": "HIGH"}, actor=task.get("id"))
            if not decision.get("allowed"):
                raise RuntimeError(f"Permission {permission} is not allowed for task {task['id']}.")

    def queue_task(self, task_id: str, priority: Optional[int] = None):
        task = self._tasks_by_id[task_id]
        if priority is not None:
            task["priority"] = priority
        status = str(task["status"]).upper()
        if status in {"QUEUED", "RUNNING", "PAUSED"}:
            self._sync_legacy_state(task)
            return task
        dependencies = list(task.get("dependencies", []))
        if dependencies:
            unresolved = [dep for dep in dependencies if str(self._tasks_by_id.get(str(dep), {}).get("status", "")).upper() != "COMPLETED"]
            if unresolved:
                self.transition(task_id, "WAITING")
                self._sync_legacy_state(task)
                return task
        self.transition(task_id, "QUEUED")
        if task_id not in self._queue:
            self._queue.append(task_id)
        self._emit("TaskQueued", task_id, priority=task["priority"])
        return task

    def start(self, task_id: str):
        task = self._tasks_by_id[task_id]
        current = str(task.get("status", "CREATED")).upper()
        if current not in {"CREATED", "QUEUED", "WAITING", "RUNNING"}:
            raise ValueError(f"Task {task_id} cannot start from status {current}.")
        self._validate_dependencies(task)
        self.transition(task_id, "RUNNING")
        task["started_at"] = task.get("started_at") or self._utcnow()
        self._emit("TaskStarted", task_id, status=task["status"])
        return task

    def pause(self, task_id: str):
        task = self._tasks_by_id[task_id]
        current = str(task.get("status", "CREATED")).upper()
        if current not in {"RUNNING", "WAITING", "PLANNING"}:
            raise ValueError(f"Task {task_id} cannot pause from status {current}.")
        self.transition(task_id, "PAUSED")
        self._emit("TaskPaused", task_id, status=task["status"])
        return task

    def resume(self, task_id: str):
        task = self._tasks_by_id[task_id]
        if str(task.get("status", "")).upper() not in {"PAUSED", "WAITING", "WAITING_FOR_APPROVAL", "RECOVERING"}:
            raise ValueError(f"Task {task_id} is not paused or waiting and cannot resume.")
        self._validate_dependencies(task)
        self._validate_permissions(task)
        self.transition(task_id, "RUNNING")
        task["recovery_decision"] = {"action": "resume", "safe_to_continue": True}
        self._emit("TaskResumed", task_id, status=task["status"])
        return task

    def cancel(self, task_id: str):
        task = self._tasks_by_id[task_id]
        if str(task.get("status", "")).upper() == "COMPLETED":
            raise ValueError("Completed tasks cannot be cancelled.")
        cancelled = self.transition(task_id, "CANCELLED")
        self._emit("TaskCancelled", task_id, status=cancelled["status"])
        return cancelled

    def fail(self, task_id: str, error: str):
        task = self._tasks_by_id[task_id]
        task["last_error"] = error
        task["errors"].append(error)
        failed = self.transition(task_id, "FAILED", reason=error)
        self._emit("TaskFailed", task_id, error=error)
        return failed

    def retry(self, task_id: str, max_retries: Optional[int] = None, reason: Optional[str] = None):
        task = self._tasks_by_id[task_id]
        if max_retries is not None:
            task["max_retries"] = max_retries
        if task["retry_count"] >= task["max_retries"]:
            self.fail(task_id, reason or "Maximum retries exceeded.")
            return self.get(task_id)
        task["retry_count"] += 1
        task["retries"] = task["retry_count"]
        self.transition(task_id, "RETRYING", reason=reason or task.get("last_error"))
        self._emit("TaskRetrying", task_id, attempt=task["retry_count"], max_retries=task["max_retries"])
        return task

    def verify(self, task_id: str, observed_result: Any, validation: Optional[Dict[str, Any]] = None):
        task = self._tasks_by_id[task_id]
        task["verification_state"] = "RUNNING"
        task["verification"] = {"expected": task.get("expected_result"), "observed": observed_result, "validation": validation or {}}
        self.transition(task_id, "VERIFYING")
        expected = task.get("expected_result")
        if expected is not None and observed_result != expected:
            raise ValueError(f"Verification failed for task {task_id}: expected {expected!r}, got {observed_result!r}.")
        if validation is not None:
            valid = bool(validation.get("verified") if isinstance(validation, dict) else validation)
            if not valid:
                raise ValueError(f"Validation failed for task {task_id}.")
        task["verification_state"] = "VERIFIED"
        task["verification"]["verified"] = True
        task["verification"]["status"] = "VERIFIED"
        self._persist()
        return task

    def complete(self, task_id: str, result: Optional[Dict[str, Any]] = None, validation: Optional[Dict[str, Any]] = None):
        task = self._tasks_by_id[task_id]
        normalized_result = result
        if result is not None and isinstance(result, dict) and "result" in result and len(result) == 1:
            normalized_result = result["result"]
        if task.get("expected_result") is not None and normalized_result != task["expected_result"]:
            raise ValueError(f"Result mismatch for task {task_id}: expected {task['expected_result']!r}, got {normalized_result!r}.")
        if validation is not None:
            valid = bool(validation.get("verified") if isinstance(validation, dict) else validation)
            if not valid:
                raise ValueError(f"Completion validation failed for task {task_id}.")
        if str(task.get("status", "")).upper() == "RUNNING":
            self.transition(task_id, "VERIFYING")
        task["verification_state"] = "VERIFIED"
        task["result"] = normalized_result
        task["outputs"].append({"result": normalized_result, "time": self._utcnow()})
        self.transition(task_id, "COMPLETED")
        self._emit("TaskCompleted", task_id, result=normalized_result)
        task["history"].append({"status": "completed", "result": normalized_result, "time": self._utcnow()})
        self._sync_legacy_state(task)
        self._persist()
        return task

    def record_checkpoint(self, task_id: str, payload: Dict[str, Any], checkpoint_type: str = "step"):
        task = self._tasks_by_id[task_id]
        checkpoint = {"id": f"cp-{len(task['checkpoints']) + 1}", "type": checkpoint_type, "time": self._utcnow(), "payload": payload}
        task["checkpoints"].append(checkpoint)
        task["updated_at"] = self._utcnow()
        task["history"].append({"checkpoint": payload, "time": self._utcnow(), "type": checkpoint_type})
        self._persist()
        return checkpoint

    def checkpoint_cleanup(self, task_id: str, keep_last: int = 3):
        task = self._tasks_by_id[task_id]
        if len(task["checkpoints"]) > keep_last:
            task["checkpoints"] = task["checkpoints"][-keep_last:]
        self._persist()
        return task["checkpoints"]

    def make_recovery_decision(self, task_id: str, error: Optional[str] = None) -> Dict[str, Any]:
        task = self._tasks_by_id[task_id]
        decision = {
            "can_retry": task.get("retry_count", 0) < task.get("max_retries", 2),
            "can_alternate_tool": bool(task.get("selected_tool")),
            "can_alternate_model": bool(task.get("selected_model")),
            "plan_change_required": bool(task.get("pending_steps")),
            "safe_to_resume": True,
            "needs_approval": False,
            "should_fail_safely": False,
            "reason": error or task.get("last_error"),
        }
        if error:
            task["last_error"] = error
        task["recovery_decision"] = decision
        self._persist()
        return decision

    def recover_task(self, task_id: str):
        task = self._tasks_by_id[task_id]
        self.transition(task_id, "RECOVERING")
        checkpoint = task["checkpoints"][-1] if task["checkpoints"] else None
        if checkpoint is not None:
            task["current_step"] = checkpoint.get("payload", {}).get("step")
        decision = self.make_recovery_decision(task_id, task.get("last_error"))
        self.transition(task_id, "RUNNING" if decision["safe_to_resume"] else "WAITING")
        self._emit("TaskRecovered", task_id, recovery=decision)
        return task

    def pending(self):
        return [task for task in self.tasks if str(task["status"]).upper() not in {"COMPLETED", "FAILED", "CANCELLED"}]

    def completed(self):
        return [task for task in self.tasks if str(task["status"]).upper() == "COMPLETED"]

    def next_ready_task(self):
        for task_id in self._queue:
            task = self._tasks_by_id[task_id]
            if str(task.get("status", "")).upper() == "QUEUED":
                return task
        return None

    def _sync_legacy_state(self, task):
        for entry in self.tasks:
            if entry.get("id") == task["id"]:
                entry["status"] = TaskStatus(task["status"])
                entry["completed"] = str(task["status"]).upper() == "COMPLETED"
                entry["task"] = task["description"]
                break

    def clear(self):
        self.tasks.clear()
        self._tasks_by_id.clear()
        self._queue.clear()
        self._persist()

    def get_task_queue(self):
        return [self._tasks_by_id[task_id] for task_id in self._queue]

    def save(self):
        self._persist()

    def load(self):
        self._load()

    def parallel(self):
        return self._queue

    def __len__(self):
        return len(self._tasks_by_id)

    def __contains__(self, task_id):
        return task_id in self._tasks_by_id

    def __iter__(self):
        return iter(self._tasks_by_id.values())

    def __getitem__(self, task_id):
        return self._tasks_by_id[task_id]

    def last_checkpoint(self, task_id: str):
        task = self._tasks_by_id[task_id]
        return task["checkpoints"][-1] if task["checkpoints"] else None

    def status(self, task_id: str):
        return str(self._tasks_by_id[task_id].get("status", "CREATED")).upper()