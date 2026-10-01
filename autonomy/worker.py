from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Autonomy Worker (Stage 10)
Author: Heeran Paul
License: MIT
--------------------------------------------

One controlled background worker over EXISTING systems only:

* kernel.Scheduler (threads) — reused, max_workers=1
* cognition.TaskManager (queue, lifecycle, persistence) — reused
* Brain.run_cycle (plan/policy/execution/verification/memory) — reused
* existing tracer — reused for autonomy events

The worker NEVER executes tools, resolves capabilities, or bypasses
policy itself: every task runs through ``Brain.run_cycle``, which
enforces permissions, capability validation, verification, budgets,
and high-risk authorization exactly as in interactive mode.

Safety properties:

* opt-in only (disabled by default — no always-on behavior)
* max 1 concurrent task; stoppable; pause stops new pickups
* only tasks flagged autonomous are picked up (interactive CLI tasks
  are never double-executed)
* retries flow through TaskManager.retry() (bounded by max_retries)
* per-run wall-clock is bounded by the loop's own time budget;
  overruns are recorded honestly, never hidden
* recurring schedules spawn child tasks (terminal states are never
  mutated — no state corruption)
* restart recovery requeues interrupted tasks via retry(); verified
  steps are never replayed (run_cycle resume machinery owns that)
"""

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from autonomy.levels import LEVEL_NAMES, evaluate_gate, normalize_level

logger = logging.getLogger("HERCULE.Autonomy")

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}
ELIGIBLE_STATES = {"QUEUED", "RETRYING"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


class AutonomyWorker:
    """Single-threaded background executor for scheduled task queue."""

    def __init__(self, services: Dict[str, Any], scheduler=None,
                 config: Optional[Dict[str, Any]] = None):
        from kernel.scheduler import Scheduler

        self.services = services
        self.brain = services["brain"]
        orchestrator = services.get("orchestrator")
        self.tasks = getattr(orchestrator, "task_manager", None)
        if self.tasks is None:
            raise RuntimeError("AutonomyWorker requires orchestrator.task_manager")
        self.scheduler = scheduler or Scheduler(max_workers=1)
        self._owns_scheduler = scheduler is None
        config = dict(config or {})
        from system.config.runtime_config import load_runtime_config
        env = load_runtime_config()
        self.enabled: bool = bool(config.get("enabled", env.autonomy_enabled))
        self.poll_interval_s: float = float(config.get("poll_interval_s", env.autonomy_poll_interval_s))
        self.max_task_runtime_s: float = float(config.get("max_task_runtime_s", env.autonomy_max_task_runtime_s))
        self.max_concurrent_tasks: int = int(config.get("max_concurrent_tasks", env.autonomy_max_concurrent_tasks))
        self.autonomy_level: int = normalize_level(config.get("autonomy_level", env.autonomy_level))
        self._stop_event = threading.Event()
        self._paused = False
        self._lock = threading.Lock()
        self._future = None
        self._worker_state = "STOPPED"
        self._active_task_id: Optional[str] = None
        self._last_result: Optional[Dict[str, Any]] = None
        self._started_count = 0
        self._completed_count = 0
        self._failed_count = 0

    # --------------------------------------------------
    # Tracing (existing tracer; best-effort, never fatal)
    # --------------------------------------------------
    def _trace(self, stage: str, data: Optional[Dict[str, Any]] = None) -> None:
        try:
            tracer = getattr(self.brain, "_tracer", None)
            if tracer is not None and hasattr(tracer, "record"):
                tracer.record(f"autonomy-{id(self):x}", stage, data or {})
        except Exception:
            pass
        try:
            logger.info("AUTONOMY %s %s", stage,
                        " ".join(f"{k}={v}" for k, v in (data or {}).items()))
        except Exception:
            pass

    # --------------------------------------------------
    # Scheduling (run once / delayed / recurring)
    # --------------------------------------------------
    def schedule(self, goal: str, delay_s: float = 0.0,
                 interval_s: Optional[float] = None,
                 priority: int = 5, timeout: int = 60,
                 max_retries: int = 2,
                 metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Queue an autonomous task. Returns {task_id, duplicate, ...}."""
        cleaned = str(goal or "").strip()
        if not cleaned:
            raise ValueError("cannot schedule an empty goal")
        if delay_s is None or float(delay_s) < 0:
            raise ValueError("delay_s must be >= 0")
        if interval_s is not None and float(interval_s) <= 0:
            raise ValueError("interval_s must be > 0 for recurring tasks")
        # Autonomy-level gate (UAI §27): deterministic risk-vs-level check
        # before anything is queued. PolicyManager still evaluates every
        # execution downstream; this only gates scheduling.
        gate = evaluate_gate(self.autonomy_level, cleaned)
        if not gate["allowed"]:
            self._trace("SCHEDULE_DENIED", {"goal": cleaned[:120], "level": self.autonomy_level,
                                            "risk": gate["risk"], "reason": gate["reason"]})
            raise PermissionError(gate["reason"])
        now_ts = _utcnow_ts()
        run_at = now_ts + float(delay_s or 0.0)
        schedule = {
            "run_at": datetime.fromtimestamp(run_at, tz=timezone.utc).isoformat(),
            "interval_s": float(interval_s) if interval_s else None,
            "recurring": bool(interval_s),
            "next_run_at": datetime.fromtimestamp(run_at, tz=timezone.utc).isoformat(),
            "occurrences": 0,
        }
        # Duplicate prevention: same goal + same schedule shape already
        # active (non-terminal) -> return the existing task honestly.
        # run_at compares with tolerance (scheduling twice in a row is
        # the same intent, not two intents).
        for task in self._autonomous_tasks():
            status = str(task.get("status", "")).upper()
            if status in TERMINAL_STATES:
                continue
            meta = task.get("metadata", {}) or {}
            existing = meta.get("schedule", {}) or {}
            if (str(task.get("goal", "")) != cleaned
                    or bool(existing.get("recurring")) != bool(interval_s)
                    or str(existing.get("interval_s") or "") != str(schedule["interval_s"] or "")):
                continue
            try:
                old_ts = datetime.fromisoformat(str(existing.get("next_run_at", ""))).timestamp()
                if abs(old_ts - run_at) > 120:
                    continue
            except Exception:
                pass
            return {"task_id": str(task.get("id")), "duplicate": True,
                    "status": status}
        merged = dict(metadata or {})
        merged.update({"autonomous": True, "schedule": schedule, "goal": cleaned})
        task_id = self.tasks.create_task(
            cleaned, timeout=int(timeout), metadata=merged,
            priority=int(priority))
        task = self.tasks.get(task_id)
        task["max_retries"] = int(max_retries)
        self.tasks.queue_task(task_id)
        self._trace("TASK_QUEUED", {"task_id": task_id, "goal": cleaned[:120],
                                   "run_at": schedule["run_at"],
                                   "recurring": schedule["recurring"]})
        try:
            self.tasks.save()
        except Exception:
            pass
        return {"task_id": task_id, "duplicate": False,
                "status": "QUEUED", "run_at": schedule["run_at"]}

    def _autonomous_tasks(self) -> List[Dict[str, Any]]:
        try:
            return [t for t in self.tasks
                    if isinstance(t, dict) and (t.get("metadata", {}) or {}).get("autonomous")]
        except Exception:
            return []

    def _due_tasks(self) -> List[Dict[str, Any]]:
        now = _utcnow()
        due = []
        for task in self._autonomous_tasks():
            if str(task.get("status", "")).upper() not in ELIGIBLE_STATES:
                continue
            sched = (task.get("metadata", {}) or {}).get("schedule", {}) or {}
            if str(sched.get("next_run_at", "")) <= now:
                due.append(task)
        due.sort(key=lambda t: (int(t.get("priority", 5)),
                                str(t.get("created_at", ""))))
        return due

    # --------------------------------------------------
    # Lifecycle: start / stop / pause / resume
    # --------------------------------------------------
    def start(self, recover: bool = True) -> Dict[str, Any]:
        """Start the background loop (opt-in). Runs recovery first.

        Levels 0 (conversation only) and 1 (suggest only) never execute,
        so start() is refused for those levels --- the worker remains a
        no-op and the caller should lower the request or run interactally.
        """
        if self.autonomy_level <= 1:
            return {"started": False,
                    "reason": (f"autonomy level {self.autonomy_level} "
                               f"({LEVEL_NAMES[self.autonomy_level]}) does not permit execution")}
        with self._lock:
            if self._future is not None and not self._future.done():
                return {"state": self._worker_state, "already_running": True}
            self._stop_event.clear()
            self._paused = False
            self._worker_state = "IDLE"
        recovered: Dict[str, Any] = {}
        if recover:
            recovered = self.recover_on_startup()
        try:
            self.brain.consciousness.set_state("AUTONOMOUS", "autonomy worker started")
        except Exception:
            pass
        self._trace("AUTONOMY_START", {"recovered": recovered})
        try:
            bus = getattr(self.brain, "event_bus", None)
            if bus is not None:
                bus.publish("AUTONOMY_STARTED", level=self.autonomy_level)
        except Exception:
            pass
        self._future = self.scheduler.submit(self._loop)
        return {"state": "IDLE", "recovered": recovered}

    def stop(self, wait: bool = True, timeout: float = 30.0) -> Dict[str, Any]:
        """Stop cleanly: no new pickups; persist state; shut down threads."""
        self._stop_event.set()
        future, scheduler = self._future, self.scheduler
        if future is not None and wait:
            try:
                future.result(timeout=timeout)
            except Exception as exc:
                logger.warning("autonomy worker stop waited: %s", exc)
        if self._owns_scheduler:
            try:
                scheduler.shutdown(wait=wait)
            except Exception as exc:
                logger.warning("autonomy scheduler shutdown: %s", exc)
        try:
            self.tasks.save()
        except Exception as exc:
            logger.warning("autonomy task persist on shutdown: %s", exc)
        with self._lock:
            self._worker_state = "STOPPED"
        try:
            self.brain.consciousness.set_state("IDLE", "autonomy worker stopped")
        except Exception:
            pass
        self._trace("AUTONOMY_STOP", {"active_task": self._active_task_id or ""})
        try:
            bus = getattr(self.brain, "event_bus", None)
            if bus is not None:
                bus.publish("AUTONOMY_STOPPED", level=self.autonomy_level)
        except Exception:
            pass
        return {"state": "STOPPED"}

    def pause(self) -> Dict[str, Any]:
        """Stop picking up new tasks (a running task finishes honestly)."""
        with self._lock:
            self._paused = True
            if self._worker_state != "STOPPED":
                self._worker_state = "PAUSED"
        try:
            self.brain.consciousness.set_state("WAITING", "autonomy paused")
        except Exception:
            pass
        return {"state": self._worker_state}

    def resume(self) -> Dict[str, Any]:
        with self._lock:
            if self._worker_state == "STOPPED":
                raise RuntimeError("autonomy worker is stopped; start it first")
            self._paused = False
            self._worker_state = "IDLE"
        try:
            self.brain.consciousness.set_state("AUTONOMOUS", "autonomy resumed")
        except Exception:
            pass
        return {"state": self._worker_state}

    @property
    def worker_state(self) -> str:
        return self._worker_state

    # --------------------------------------------------
    # Restart recovery (load, verify, resume safely)
    # --------------------------------------------------
    def recover_on_startup(self) -> Dict[str, Any]:
        """Reconcile persisted autonomous tasks after a restart.

        Stale RUNNING/RECOVERING -> retry() (keeps checkpoints; verified
        steps are never replayed by run_cycle's resume machinery).
        Stale RETRYING stays eligible as-is. PAUSED/WAITING/QUEUED and
        FAILED-with-budget are left for normal pickup. Terminal tasks
        are never mutated. Returns an honest summary.
        """
        summary: Dict[str, Any] = {"resumed": [], "left_paused": [],
                                   "left_queued": [], "failed_now": []}
        try:
            self.tasks.load()
        except Exception as exc:
            logger.warning("autonomy recovery load: %s", exc)
        for task in self._autonomous_tasks():
            task_id = str(task.get("id"))
            status = str(task.get("status", "")).upper()
            try:
                if status in ("RUNNING", "RECOVERING"):
                    self.tasks.retry(task_id, reason="interrupted by restart; safe resume")
                    summary["resumed"].append(task_id)
                    self._trace("TASK_QUEUED", {"task_id": task_id,
                                               "reason": "restart-recovery"})
                elif status == "PAUSED":
                    summary["left_paused"].append(task_id)
                elif status in ("QUEUED", "WAITING", "RETRYING"):
                    summary["left_queued"].append(task_id)
                elif status == "FAILED":
                    if int(task.get("retry_count", 0) or 0) < int(task.get("max_retries", 2)):
                        self.tasks.retry(task_id, reason="restart recovery; retries remain")
                        summary["resumed"].append(task_id)
            except Exception as exc:
                summary["failed_now"].append({"task_id": task_id, "error": str(exc)[:160]})
        try:
            self.tasks.save()
        except Exception:
            pass
        return summary

    # --------------------------------------------------
    # Main loop (single task at a time)
    # --------------------------------------------------
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._paused:
                    with self._lock:
                        if self._worker_state != "STOPPED":
                            self._worker_state = "PAUSED"
                    self._stop_event.wait(self.poll_interval_s)
                    continue
                with self._lock:
                    if self._worker_state != "STOPPED":
                        self._worker_state = "IDLE"
                due = self._due_tasks()
                if not due:
                    with self._lock:
                        if self._worker_state != "STOPPED":
                            self._worker_state = "WAITING"
                    try:
                        self.brain.consciousness.set_state("WAITING", "autonomy idle; queue empty")
                    except Exception:
                        pass
                    self._stop_event.wait(self.poll_interval_s)
                    continue
                self._execute_one(due[0])
            except Exception as exc:
                logger.error("autonomy worker loop error: %s", exc)
                self._stop_event.wait(self.poll_interval_s)

    def _execute_one(self, task: Dict[str, Any]) -> None:
        task_id = str(task.get("id"))
        goal = str(task.get("goal", task.get("description", "")))
        with self._lock:
            self._worker_state = "RUNNING"
            self._active_task_id = task_id
        try:
            self.brain.consciousness.set_state("AUTONOMOUS", f"executing:{task_id}")
        except Exception:
            pass
        # Eligible RETRYING tasks enter RUNNING directly; QUEUED via start()
        # (validates dependencies — unmet deps park the task honestly).
        try:
            current = str(self.tasks.get(task_id).get("status", "")).upper()
            if current == "RETRYING":
                self.tasks.transition(task_id, "RUNNING")
            else:
                self.tasks.start(task_id)
        except Exception as exc:
            self._trace("TASK_FAILED", {"task_id": task_id,
                                       "error": f"start refused: {exc}"[:160]})
            with self._lock:
                self._active_task_id = None
            return
        self._trace("TASK_STARTED", {"task_id": task_id, "goal": goal[:120]})
        started = time.perf_counter()
        try:
            result = self.brain.run_cycle(goal, task_id=task_id)
        except Exception as exc:
            try:
                self.tasks.fail(task_id, str(exc)[:300])
            except Exception:
                pass
            result = {"status": "failed", "error": str(exc)[:300]}
        elapsed = time.perf_counter() - started
        status = str((result or {}).get("status", "failed")).lower()
        over_budget = elapsed > self.max_task_runtime_s
        # Per-step outcomes already recorded by the loop; emit worker-level
        # STEP_* events from durable capability states (never invented).
        self._emit_step_events(task_id)
        if status == "failed":
            try:
                task_now = self.tasks.get(task_id)
                if int(task_now.get("retry_count", 0) or 0) < int(task_now.get("max_retries", 2)):
                    self.tasks.retry(task_id, reason=str((result or {}).get("error", ""))[:200])
                    self._trace("REPLAN", {"task_id": task_id,
                                          "action": "worker-retry-queued"})
                # else: FAILED stands; run_cycle already failed it honestly.
            except Exception as exc:
                logger.warning("autonomy retry bookkeeping: %s", exc)
        if str(self.tasks.get(task_id).get("status", "")).upper() == "COMPLETED":
            self._completed_count += 1
            self._trace("TASK_COMPLETED", {"task_id": task_id,
                                          "elapsed_s": round(elapsed, 1)})
            self._maybe_reschedule(task_id)
        else:
            self._failed_count += 1
            self._trace("TASK_FAILED", {"task_id": task_id,
                                       "status": status,
                                       "elapsed_s": round(elapsed, 1)})
        if over_budget:
            # The outcome stands (it really happened); the overrun is
            # recorded honestly in logs and last_result, and operators
            # can tighten max_task_runtime_s or the loop time budget.
            logger.warning("autonomy task %s overran budget: %.1fs > %.1fs (outcome stands, it was real)",
                           task_id, elapsed, self.max_task_runtime_s)
        # Concise background-task experience is recorded by run_cycle's own
        # memory path; the worker only persists task state.
        try:
            self.tasks.save()
        except Exception:
            pass
        with self._lock:
            self._active_task_id = None
            if self._worker_state != "STOPPED":
                self._worker_state = "IDLE"
        self._last_result = {"task_id": task_id, "status": status,
                             "summary": str((result or {}).get("execution_summary", ""))[:200],
                             "at": _utcnow(), "elapsed_s": round(elapsed, 1),
                             "over_budget": over_budget}

    def _emit_step_events(self, task_id: str) -> None:
        try:
            states = ((self.tasks.get(task_id).get("metadata", {}) or {})
                      .get("capability_states", {}) or {})
            replans = 0
            for step_id in sorted(states):
                state = states[step_id] or {}
                verification = state.get("verification") or {}
                if verification.get("passed"):
                    self._trace("STEP_COMPLETED", {"task_id": task_id, "step_id": step_id})
                elif state.get("status"):
                    self._trace("STEP_FAILED", {"task_id": task_id, "step_id": step_id,
                                               "detail": str(state.get("failure", ""))[:160]})
                if int(state.get("retries", 0) or 0) > 0:
                    replans += 1
            if replans:
                self._trace("REPLAN", {"task_id": task_id, "retried_steps": replans})
        except Exception:
            pass

    def _maybe_reschedule(self, task_id: str) -> None:
        try:
            task = self.tasks.get(task_id)
            sched = (task.get("metadata", {}) or {}).get("schedule", {}) or {}
            if not sched.get("recurring") or not sched.get("interval_s"):
                return
            nxt = _utcnow_ts() + float(sched["interval_s"])
            child_meta = {"autonomous": True, "goal": str(task.get("goal", "")),
                          "schedule": {**sched,
                                       "next_run_at": datetime.fromtimestamp(
                                           nxt, tz=timezone.utc).isoformat(),
                                       "occurrences": int(sched.get("occurrences", 0)) + 1}}
            child_id = self.tasks.create_task(
                str(task.get("goal", "")), timeout=int(task.get("timeout", 60)),
                metadata=child_meta, priority=int(task.get("priority", 5)),
                parent_task_id=task_id)
            child = self.tasks.get(child_id)
            child["max_retries"] = int(task.get("max_retries", 2))
            self.tasks.queue_task(child_id)
            self._trace("TASK_QUEUED", {"task_id": child_id, "recurring_child_of": task_id,
                                       "next_run_at": child_meta["schedule"]["next_run_at"]})
        except Exception as exc:
            logger.warning("autonomy reschedule: %s", exc)

    # --------------------------------------------------
    # Status snapshot for UI (UNKNOWN, never fabricated)
    # --------------------------------------------------
    def status(self) -> Dict[str, Any]:
        try:
            queued = [str(t.get("id")) for t in self._due_tasks()]
            all_auto = self._autonomous_tasks()
            counts: Dict[str, int] = {}
            for task in all_auto:
                key = str(task.get("status", "UNKNOWN")).upper()
                counts[key] = counts.get(key, 0) + 1
            return {
                "enabled": self.enabled,
                "worker_state": self._worker_state,
                "max_concurrent_tasks": self.max_concurrent_tasks,
                "max_task_runtime_s": self.max_task_runtime_s,
                "queued": queued,
                "active_task": self._active_task_id or "",
                "last_result": dict(self._last_result or {}),
                "counts": counts,
                "started": self._started_count,
                "completed": self._completed_count,
                "failed": self._failed_count,
            }
        except Exception as exc:
            return {"enabled": self.enabled, "worker_state": "UNKNOWN",
                    "error": str(exc)[:160]}

    def set_enabled(self, enabled: bool) -> Dict[str, Any]:
        self.enabled = bool(enabled)
        return {"enabled": self.enabled}
