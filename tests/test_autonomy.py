"""Stage 10: background autonomy worker, scheduler integration, recovery.

Fast hermetic tests: mock model backend, :memory: or tmp task stores.
No live LLM, no real waiting longer than small poll windows.
"""
import time

import pytest


def mock_env(monkeypatch, tmp_path=None):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    if tmp_path is not None:
        monkeypatch.setenv("HERCULE_TASK_STORE", str(tmp_path / "tasks.json"))
    else:
        monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")


@pytest.fixture()
def services(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from runtime.initializer import RuntimeInitializer
    return RuntimeInitializer().initialize()


@pytest.fixture()
def worker(services):
    from autonomy.worker import AutonomyWorker
    w = AutonomyWorker(services, config={"poll_interval_s": 0.05})
    yield w
    try:
        w.stop(wait=True)
    except Exception:
        pass


def wait_for(predicate, timeout=15.0, interval=0.05):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------- scheduler integration ----------

def test_scheduler_runs_job_and_shuts_down():
    from kernel.scheduler import Scheduler
    scheduler = Scheduler(max_workers=1)
    try:
        future = scheduler.submit(lambda: 40 + 2)
        assert future.result(timeout=10) == 42
    finally:
        scheduler.shutdown(wait=True)


def test_worker_disabled_by_default(services):
    from autonomy.worker import AutonomyWorker
    assert AutonomyWorker(services).enabled is False


# ---------- queue ----------

def test_schedule_queues_autonomous_task(worker, services):
    outcome = worker.schedule("calculate 2+2")
    assert outcome["duplicate"] is False
    assert outcome["status"] == "QUEUED"
    tasks = services["orchestrator"].task_manager
    task = tasks.get(outcome["task_id"])
    assert (task.get("metadata", {}) or {}).get("autonomous") is True
    assert any(t["id"] == outcome["task_id"] for t in tasks.get_task_queue())


def test_schedule_rejects_empty_goal(worker):
    with pytest.raises(ValueError):
        worker.schedule("   ")


def test_duplicate_schedule_returns_existing(worker):
    first = worker.schedule("calculate 2+2")
    second = worker.schedule("calculate 2+2")
    assert second["duplicate"] is True
    assert second["task_id"] == first["task_id"]


def test_delayed_task_not_due_yet(worker):
    outcome = worker.schedule("calculate 2+2", delay_s=3600)
    assert outcome["status"] == "QUEUED"
    assert worker._due_tasks() == []


# ---------- background worker execution ----------

def test_worker_executes_scheduled_task(worker):
    outcome = worker.schedule("calculate 2+2")
    worker.start(recover=False)
    try:
        task_id = outcome["task_id"]
        assert wait_for(
            lambda: worker.tasks.get(task_id).get("status") in ("COMPLETED", "FAILED"),
            timeout=20.0)
        assert wait_for(lambda: worker._completed_count >= 1, timeout=20.0)
        task = worker.tasks.get(task_id)
        assert str(task.get("status")) == "COMPLETED"
        states = (task.get("metadata", {}) or {}).get("capability_states", {}) or {}
        assert states, "verified step states must be recorded"
    finally:
        worker.stop()


def test_worker_pause_and_resume(worker):
    worker.start(recover=False)
    try:
        worker.pause()
        assert worker.worker_state == "PAUSED"
        outcome = worker.schedule("calculate 3+3")
        time.sleep(0.4)
        assert str(worker.tasks.get(outcome["task_id"]).get("status")) == "QUEUED"
        worker.resume()
        assert wait_for(
            lambda: str(worker.tasks.get(outcome["task_id"]).get("status")) == "COMPLETED",
            timeout=20.0)
    finally:
        worker.stop()


def test_worker_cancel_task(worker, services):
    outcome = worker.schedule("calculate 4+4", delay_s=3600)
    services["orchestrator"].task_manager.cancel(outcome["task_id"])
    worker.start(recover=False)
    try:
        time.sleep(0.4)
        assert str(worker.tasks.get(outcome["task_id"]).get("status")) == "CANCELLED"
    finally:
        worker.stop()


def test_clean_shutdown_is_idempotent(worker):
    worker.start(recover=False)
    first = worker.stop()
    second = worker.stop()
    assert first["state"] == "STOPPED"
    assert second["state"] == "STOPPED"


# ---------- restart recovery ----------

def test_restart_recovery_requeues_interrupted(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from runtime.initializer import RuntimeInitializer
    from autonomy.worker import AutonomyWorker

    services = RuntimeInitializer().initialize()
    tasks = services["orchestrator"].task_manager
    task_id = tasks.create_task("calculate 5+5",
                                metadata={"autonomous": True, "goal": "calculate 5+5"})
    tasks.queue_task(task_id)
    tasks.start(task_id)
    tasks.record_checkpoint(task_id, {"step": "step-1"}, checkpoint_type="step")
    tasks.save()

    # Simulated restart: brand-new services over the same store.
    services2 = RuntimeInitializer().initialize()
    worker2 = AutonomyWorker(services2, config={"poll_interval_s": 0.05})
    try:
        summary = worker2.recover_on_startup()
        assert task_id in summary["resumed"]
        assert str(services2["orchestrator"].task_manager.get(task_id).get("status")) == "RETRYING"
        # Checkpoints survive; verified steps are never replayed blindly.
        assert services2["orchestrator"].task_manager.get(task_id)["checkpoints"]
    finally:
        worker2.stop()


def test_restart_recovery_executes_resumed_task(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from runtime.initializer import RuntimeInitializer
    from autonomy.worker import AutonomyWorker

    services = RuntimeInitializer().initialize()
    worker = AutonomyWorker(services, config={"poll_interval_s": 0.05})
    scheduled = worker.schedule("calculate 6+6")
    worker.stop()
    # Drop the in-memory state; reload from disk like a fresh process.
    services2 = RuntimeInitializer().initialize()
    worker2 = AutonomyWorker(services2, config={"poll_interval_s": 0.05})
    try:
        worker2.start(recover=True)
        assert wait_for(
            lambda: str(services2["orchestrator"].task_manager.get(
                scheduled["task_id"]).get("status")) == "COMPLETED",
            timeout=20.0)
    finally:
        worker2.stop()


def test_paused_tasks_survive_recovery_untouched(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from runtime.initializer import RuntimeInitializer
    from autonomy.worker import AutonomyWorker

    services = RuntimeInitializer().initialize()
    worker = AutonomyWorker(services, config={"poll_interval_s": 0.05})
    scheduled = worker.schedule("calculate 7+7")
    tasks = services["orchestrator"].task_manager
    tasks.start(scheduled["task_id"])
    tasks.pause(scheduled["task_id"])
    tasks.save()
    worker.stop()

    services2 = RuntimeInitializer().initialize()
    worker2 = AutonomyWorker(services2, config={"poll_interval_s": 0.05})
    try:
        summary = worker2.recover_on_startup()
        assert scheduled["task_id"] in summary["left_paused"]
        assert str(services2["orchestrator"].task_manager.get(
            scheduled["task_id"]).get("status")) == "PAUSED"
    finally:
        worker2.stop()


# ---------- budgets / policy / high-risk ----------

def test_over_budget_outcome_stands_but_flagged(worker):
    worker.max_task_runtime_s = 0.0  # any real execution exceeds this
    outcome = worker.schedule("calculate 8+8")
    worker.start(recover=False)
    try:
        task_id = outcome["task_id"]
        assert wait_for(lambda: worker._last_result is not None, timeout=20.0)
        assert str(worker.tasks.get(task_id).get("status")) == "COMPLETED"
        assert worker._last_result["over_budget"] is True
        assert worker._last_result["status"] == "completed"
    finally:
        worker.stop()


def test_permission_denial_fails_honestly(worker, services):
    # Deny through whichever policy object the AbilityManager consults.
    abilities = services["orchestrator"].abilities
    manager_policy = getattr(abilities, "policy", None)
    security = services.get("security")
    target = manager_policy or (getattr(security, "policy", None) if security else None)
    assert target is not None
    target.set_permission("MATH", False)
    try:
        outcome = worker.schedule("calculate 9+9")
        worker.start(recover=False)
        try:
            task_id = outcome["task_id"]
            assert wait_for(
                lambda: str(worker.tasks.get(task_id).get("status")) == "FAILED",
                timeout=20.0)
            task = worker.tasks.get(task_id)
            report = (task.get("metadata", {}) or {}).get("autonomy_report", {}) or {}
            problems = [p for f in report.get("failed", []) if isinstance(f, dict)
                        for p in (f.get("problems", []) or [])]
            assert any(p.get("code") == "PERMISSION_CONFLICT" for p in problems), problems
            states = (task.get("metadata", {}) or {}).get("capability_states", {}) or {}
            assert not any(str((s or {}).get("status", "")).lower() == "completed"
                           for s in states.values()), "denied ability must never execute"
        finally:
            worker.stop()
    finally:
        target.set_permission("MATH", True)


def test_high_risk_requires_approval(worker):
    outcome = worker.schedule("run the terminal command `rm -rf /` now")
    worker.start(recover=False)
    try:
        task_id = outcome["task_id"]
        assert wait_for(
            lambda: str(worker.tasks.get(task_id).get("status")) in ("FAILED", "COMPLETED"),
            timeout=25.0)
        task = worker.tasks.get(task_id)
        # Must never succeed without explicit approval.
        assert str(task.get("status")) == "FAILED"
        report = (task.get("metadata", {}) or {}).get("autonomy_report", {}) or {}
        blob = str(report.get("failed", ""))
        assert ("pproval" in blob) or ("ermission" in blob) or ("enied" in blob), blob[:500]
        states = (task.get("metadata", {}) or {}).get("capability_states", {}) or {}
        assert not any(str((s or {}).get("status", "")).lower() == "completed"
                       for s in states.values()), "unapproved high-risk step must never complete"
    finally:
        worker.stop()


# ---------- resume robustness ----------

def test_retry_after_match_failure_does_not_crash_resume(worker, services):
    # Match failures (no healthy provider) persist capability states with
    # verification=None; a subsequent retry + resume must treat them as
    # unverified, not crash with AttributeError.
    abilities = services["orchestrator"].abilities
    abilities.ensure_defaults()
    abilities.get("files").disable()
    try:
        outcome = worker.schedule("create a file named retry_probe.txt containing x")
        worker.start(recover=False)
        try:
            task_id = outcome["task_id"]
            assert wait_for(
                lambda: str(worker.tasks.get(task_id).get("status")) in (
                    "FAILED", "PAUSED", "BLOCKED"),
                timeout=20.0)
            assert str(worker.tasks.get(task_id).get("status")) != "COMPLETED"
            states = ((worker.tasks.get(task_id).get("metadata", {}) or {})
                      .get("capability_states", {}) or {})
            assert any((s or {}).get("verification") is None for s in states.values())
            abilities.get("files").enable()
            current = str(worker.tasks.get(task_id).get("status"))
            if current == "PAUSED":
                worker.tasks.resume(task_id)
            else:
                worker.tasks.retry(task_id)
                worker.tasks.transition(task_id, "RUNNING")
            result = services["brain"].run_cycle(
                "create a file named retry_probe.txt containing x", task_id=task_id)
            assert result["status"] in ("completed", "partial", "failed", "blocked")
        finally:
            worker.stop()
    finally:
        abilities.get("files").enable()


# ---------- UI snapshot ----------

def test_ui_autonomy_snapshot(monkeypatch):
    mock_env(monkeypatch, None)
    from runtime.initializer import RuntimeInitializer
    from interface.app_controller import HerculeAppController
    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    try:
        snap = controller.autonomy_snapshot()
        assert snap["enabled"] is False
        assert snap["worker_state"] in ("STOPPED", "UNKNOWN")
        assert "queued" in snap and "active_task" in snap and "last_result" in snap
        full = controller.snapshot()
        assert "autonomy" in full
        started = controller.start_autonomy()
        assert started["state"] in ("IDLE", "WAITING", "RUNNING")
        assert controller.autonomy_snapshot()["enabled"] is True
        stopped = controller.stop_autonomy()
        assert stopped["state"] == "STOPPED"
    finally:
        try:
            controller.shutdown_autonomy()
        except Exception:
            pass
