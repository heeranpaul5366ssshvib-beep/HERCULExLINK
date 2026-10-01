from __future__ import annotations
"""Phase H: lifecycle EventBus verification (UAI §29).

Uses the existing kernel EventBus only. Covers bus semantics,
failure isolation (bus faults never break the pipeline), worker
autonomy events, and the full Brain run_cycle event sequence.
"""

import threading

import pytest

from kernel.event_bus import EventBus


@pytest.fixture()
def bus():
    return EventBus()


def test_bus_pubsub_and_unsubscribe(bus):
    seen = []
    bus.subscribe("E1", lambda **kw: seen.append(kw))
    bus.publish("E1", value=1)
    assert seen == [{"value": 1}]
    handler = lambda **kw: seen.append("second")
    bus.subscribe("E1", handler)
    bus.unsubscribe("E1", handler)
    bus.publish("E1", value=2)
    assert seen == [{"value": 1}, {"value": 2}]


def test_bus_dedupes_repeat_subscription(bus):
    calls = []
    handler = lambda **kw: calls.append(1)
    bus.subscribe("E", handler)
    bus.subscribe("E", handler)
    bus.publish("E")
    assert calls == [1]


def test_bus_clear(bus):
    bus.subscribe("E", lambda **kw: None)
    bus.clear()
    bus.publish("E")  # no subscribers, no error


def test_brain_emit_swallows_bus_failure():
    import brain.brain as brain_mod

    class _ExplodingBus(EventBus):
        def publish(self, event, *args, **kwargs):
            raise RuntimeError("subscriber exploded")

    class _Holder:
        event_bus = _ExplodingBus()

    # Must not raise: observability never breaks the pipeline.
    brain_mod.Brain._emit_event(_Holder(), "USER_REQUEST", correlation_id="c")


def test_brain_emit_without_bus_is_noop():
    import brain.brain as brain_mod

    class _Holder:
        event_bus = None

    brain_mod.Brain._emit_event(_Holder(), "GOAL_CREATED")


def test_task_manager_emit_failure_does_not_break_transitions():
    from cognition.task_manager.task_manager import TaskManager

    class _ExplodingBus(EventBus):
        def publish(self, event, *args, **kwargs):
            raise RuntimeError("subscriber exploded")

    tasks = TaskManager(event_bus=_ExplodingBus())
    tid = tasks.create_task("lifecycle goal")
    tasks.queue_task(tid)
    tasks.start(tid)
    tasks.complete(tid, result={})
    assert str(tasks.get(tid).get("status")) == "COMPLETED"


def _bare_worker(bus):
    from autonomy.worker import AutonomyWorker

    class _DoneFuture:
        def done(self):
            return True

        def result(self, timeout=None):
            return None

    class _StubScheduler:
        def submit(self, fn):
            return _DoneFuture()

        def shutdown(self, wait=True):
            pass

    class _Consciousness:
        def set_state(self, *a, **k):
            pass

    worker = AutonomyWorker.__new__(AutonomyWorker)
    worker.services = {}
    worker.brain = type("B", (), {"consciousness": _Consciousness(),
                                  "event_bus": bus})()
    worker.tasks = type("T", (), {"save": lambda self: None})()
    worker.enabled = True
    worker.autonomy_level = 2
    worker.scheduler = _StubScheduler()
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


def test_worker_publishes_autonomy_started_stopped():
    bus = EventBus()
    seen = []
    bus.subscribe("AUTONOMY_STARTED", lambda **kw: seen.append(("STARTED", kw)))
    bus.subscribe("AUTONOMY_STOPPED", lambda **kw: seen.append(("STOPPED", kw)))
    worker = _bare_worker(bus)
    worker.start(recover=False)
    worker.stop(wait=False)
    assert [s[0] for s in seen] == ["STARTED", "STOPPED"]
    assert seen[0][1]["level"] == 2


def test_run_cycle_event_sequence(monkeypatch, tmp_path):
    """Full pipeline emits the ordered lifecycle sequence (mock model)."""
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    bus = services["orchestrator"].event_bus
    order = []
    for event in ("USER_REQUEST", "GOAL_CREATED", "PLAN_CREATED",
                  "OBSERVATION_RECEIVED", "VERIFICATION_COMPLETED",
                  "REFLECTION_COMPLETED", "GOAL_COMPLETED", "GOAL_FAILED"):
        bus.subscribe(event, lambda _e=event, **kw: order.append(_e))
    report = services["brain"].run_cycle("calculate 2+2")
    assert report["status"] == "completed"
    for event in ("USER_REQUEST", "GOAL_CREATED", "PLAN_CREATED",
                  "OBSERVATION_RECEIVED", "VERIFICATION_COMPLETED",
                  "REFLECTION_COMPLETED", "GOAL_COMPLETED"):
        assert event in order, order
    assert order.index("USER_REQUEST") < order.index("GOAL_CREATED")
    assert order.index("GOAL_CREATED") < order.index("PLAN_CREATED")
    assert order.index("PLAN_CREATED") < order.index("OBSERVATION_RECEIVED")
    assert order.index("VERIFICATION_COMPLETED") < order.index("GOAL_COMPLETED")
