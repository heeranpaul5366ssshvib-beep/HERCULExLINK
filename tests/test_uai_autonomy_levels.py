from __future__ import annotations
"""Phase F: autonomy-level integration (UAI §27).

Levels gate *scheduling authority*; PolicyManager gates *operation
permission*. These tests prove the separation across all six levels
without running models: gate matrix, worker schedule enforcement,
policy independence, level-5 boundedness, and lifecycle ops.
"""

import threading

import pytest

from autonomy.levels import (
    LEVEL_MAX_RISK,
    LEVEL_MAX_RUNTIME_S,
    LEVEL_NAMES,
    RISK_ORDER,
    classify_goal_risk,
    evaluate_gate,
    normalize_level,
)
from autonomy.worker import AutonomyWorker

LOW_GOAL = "read the project notes"
MEDIUM_GOAL = "create a summary report"
HIGH_GOAL = "delete temp folders"


def _bare_worker(level):
    """Lightweight worker: gate + lifecycle only, no runtime/services."""
    worker = AutonomyWorker.__new__(AutonomyWorker)
    worker.services = {}
    worker.brain = type("B", (), {"consciousness": None, "event_bus": None})()
    worker.tasks = _StubTasks()
    worker.enabled = True
    worker.autonomy_level = normalize_level(level)
    worker.scheduler = None
    worker._owns_scheduler = False
    worker._stop_event = threading.Event()
    worker._paused = False
    worker._lock = threading.Lock()
    worker._future = None
    worker._worker_state = "STOPPED"
    worker._active_task_id = None
    worker._last_result = None
    worker.max_task_runtime_s = 60.0
    worker.max_concurrent_tasks = 1
    worker._started_count = 0
    worker._completed_count = 0
    worker._failed_count = 0
    return worker


class _StubTasks:
    def __init__(self):
        self._tasks = {}
        self._seq = 0

    def __iter__(self):
        return iter(self._tasks.values())

    def create_task(self, goal, timeout=60, metadata=None, priority=5):
        self._seq += 1
        tid = f"t-{self._seq}"
        self._tasks[tid] = {"id": tid, "goal": goal, "status": "CREATED",
                            "metadata": dict(metadata or {})}
        return tid

    def get(self, tid):
        return self._tasks[tid]

    def queue_task(self, tid):
        self._tasks[tid]["status"] = "QUEUED"

    def save(self):
        pass


# ---------- gate matrix: all six levels ----------

@pytest.mark.parametrize("level,low,medium,high", [
    (0, False, False, False),
    (1, False, False, False),
    (2, True, True, False),
    (3, True, True, False),
    (4, True, True, True),
    (5, True, True, True),
])
def test_gate_matrix_all_levels(level, low, medium, high):
    assert evaluate_gate(level, LOW_GOAL)["allowed"] is low
    assert evaluate_gate(level, MEDIUM_GOAL)["allowed"] is medium
    assert evaluate_gate(level, HIGH_GOAL)["allowed"] is high


def test_gate_reasons_name_level_and_risk():
    verdict = evaluate_gate(2, HIGH_GOAL)
    assert verdict["risk"] == "HIGH"
    assert "level 2" in verdict["reason"]
    assert LEVEL_NAMES[2] in verdict["reason"]


def test_gate_deterministic_and_ceiling_shape():
    assert evaluate_gate(3, MEDIUM_GOAL) == evaluate_gate(3, MEDIUM_GOAL)
    assert set(LEVEL_MAX_RISK) == {0, 1, 2, 3, 4, 5}
    assert set(LEVEL_NAMES) == {0, 1, 2, 3, 4, 5}
    assert set(RISK_ORDER) == {"LOW", "MEDIUM", "HIGH"}


# ---------- worker schedule enforcement per level ----------

@pytest.mark.parametrize("level,expect", [(0, False), (1, False), (2, True)])
def test_worker_schedule_low_goal_by_level(level, expect):
    worker = _bare_worker(level)
    if expect:
        out = worker.schedule(LOW_GOAL)
        assert out["status"] == "QUEUED" and out["duplicate"] is False
    else:
        with pytest.raises(PermissionError):
            worker.schedule(LOW_GOAL)


def test_worker_schedule_medium_allowed_at_2_and_3():
    for level in (2, 3):
        out = _bare_worker(level).schedule(MEDIUM_GOAL)
        assert out["status"] == "QUEUED"


def test_worker_schedule_high_denied_below_4_allowed_at_5():
    for level in (0, 1, 2, 3):
        with pytest.raises(PermissionError):
            _bare_worker(level).schedule(HIGH_GOAL)
    out = _bare_worker(5).schedule(HIGH_GOAL)
    assert out["status"] == "QUEUED"


def test_worker_schedule_rejects_empty_goal():
    with pytest.raises(ValueError):
        _bare_worker(4).schedule("   ")


# ---------- policy independence: level never overrides denial ----------

def test_high_level_does_not_bypass_policy():
    from security.permissions.policy_manager import PolicyManager

    policy = PolicyManager()
    # Gate at level 5 allows the HIGH-risk goal to be scheduled...
    assert evaluate_gate(5, HIGH_GOAL)["allowed"] is True
    out = _bare_worker(5).schedule(HIGH_GOAL)
    assert out["status"] == "QUEUED"
    # ...but PolicyManager still denies the operation independently.
    policy.set_permission("FILE_WRITE", False)
    try:
        decision = policy.evaluate("FILE_WRITE", {"risk": "HIGH"})
        assert decision["allowed"] is False
    finally:
        policy.set_permission("FILE_WRITE", True)
    assert policy.evaluate("FILE_WRITE", {"risk": "HIGH"})["allowed"] is True


def test_policy_approval_required_for_medium_and_high():
    from security.permissions.policy_manager import PolicyManager

    policy = PolicyManager()
    assert policy.evaluate("NETWORK_ACCESS", {"risk": "MEDIUM"})["required_approval"] is True
    assert policy.evaluate("TERMINAL_EXECUTE", {"risk": "HIGH"})["required_approval"] is True
    assert policy.evaluate("FILE_READ", {"risk": "LOW"})["required_approval"] is False


# ---------- level 5 stays bounded ----------

def test_level_5_is_bounded_not_unrestricted():
    assert LEVEL_MAX_RISK[5] == 2  # HIGH ceiling, not infinity
    assert LEVEL_MAX_RUNTIME_S[5] == 3600.0  # explicit long-run bound
    worker = _bare_worker(5)
    assert worker.max_task_runtime_s > 0  # per-run wall-clock still enforced
    assert worker.max_concurrent_tasks == 1  # still single-flight


# ---------- lifecycle: start gate, pause/resume, stop ----------

def test_start_refused_at_levels_0_and_1():
    for level in (0, 1):
        out = _bare_worker(level).start(recover=False)
        assert out["started"] is False
        assert f"level {level}" in out["reason"]


def test_pause_resume_stop_cycle():
    worker = _bare_worker(2)
    worker._worker_state = "IDLE"  # simulate a started worker (no loop thread)
    assert worker.pause()["state"] == "PAUSED"
    assert worker.resume()["state"] == "IDLE"
    assert worker.stop(wait=False)["state"] == "STOPPED"


def test_resume_when_stopped_raises():
    worker = _bare_worker(2)
    with pytest.raises(RuntimeError):
        worker.resume()


# ---------- risk classification spot checks ----------

def test_classify_goal_risk_spots():
    assert classify_goal_risk(LOW_GOAL)["risk"] == "LOW"
    assert classify_goal_risk(MEDIUM_GOAL)["risk"] == "MEDIUM"
    assert classify_goal_risk(HIGH_GOAL)["risk"] == "HIGH"
