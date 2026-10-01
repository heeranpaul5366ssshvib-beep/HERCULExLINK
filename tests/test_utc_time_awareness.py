"""Phase E regression tests: timezone-aware UTC across the intelligence layer.

External format is preserved as ISO-8601 strings; the only intended change
vs the legacy naive UTC-now isoformat output is the
``+00:00`` UTC offset suffix. All internal datetime objects must be
timezone-aware so that arithmetic/comparison never raises::

    TypeError: can't compare offset-naive and offset-aware datetimes
"""

from datetime import datetime, timezone

from cognition.task_manager.task_manager import TaskManager
from intelligence.coordination.coordinator_metrics import CoordinatorMetrics
from intelligence.coordination.coordinator_state import CoordinatorStateManager
from intelligence.coordination.execution_graph import ExecutionGraph
from intelligence.coordination.synchronization import SynchronizationManager
from intelligence.intelligence_core import IntelligenceCore
from intelligence.runtime.execution_context import ExecutionContext
from intelligence.runtime.execution_state import ExecutionState
from intelligence.runtime.runtime_cache import RuntimeCache
from intelligence.runtime.runtime_metrics import RuntimeMetrics
from intelligence.runtime.runtime_monitor import RuntimeMonitor
from intelligence.world_model import WorldModel


def _assert_aware_iso(ts: str):
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None, f"naive timestamp: {ts!r}"
    assert parsed.utcoffset() is not None, f"missing utcoffset: {ts!r}"
    return parsed


def test_world_model_timestamps_are_timezone_aware():
    model = WorldModel(kernel=None)
    model.add_relationship("A", "knows", "B")
    payload = model.process({})
    first = _assert_aware_iso(payload["timestamp"])
    assert first.tzinfo is not None
    rel_ts = _assert_aware_iso(model.relationships[0]["timestamp"])
    # UTC semantics preserved: offset must be zero.
    assert first.utcoffset().total_seconds() == 0
    assert rel_ts.utcoffset().total_seconds() == 0


def test_runtime_cache_and_monitor_keep_aware_utc_timestamps():
    cache = RuntimeCache()
    cache.put("demo", "value", ttl=60)
    assert cache.get("demo") == "value"

    monitor = RuntimeMonitor()
    monitor.record("test.event", {"result": "ok"})
    event = monitor.events[0]
    _assert_aware_iso(event["timestamp"])

    metrics = RuntimeMetrics()
    metrics.record(0.25, success=True)
    _assert_aware_iso(metrics.report()["started"])


def test_runtime_cache_expiry_uses_aware_comparison():
    cache = RuntimeCache()
    cache.put("short", "v", ttl=100)
    entry = cache.cache["short"]
    assert entry.created.tzinfo is not None
    assert entry.expires.tzinfo is not None
    # Must not raise TypeError: aware vs aware comparison.
    assert entry.expired in (True, False)
    assert cache.get("short") == "v"

    cache.put("neg", "gone", ttl=-1)
    assert cache.get("neg") is None


def test_runtime_metrics_report_stays_aware():
    metrics = RuntimeMetrics()
    assert metrics.started.tzinfo is not None
    report = metrics.report()
    _assert_aware_iso(report["started"])
    metrics.reset()
    assert metrics.started.tzinfo is not None


def test_execution_state_lifecycle_stays_aware():
    state = ExecutionState()
    assert state.created.tzinfo is not None
    state.start()
    state.complete()
    assert state.started.tzinfo is not None
    assert state.finished.tzinfo is not None
    # Aware minus aware must not raise.
    duration = (state.finished - state.started).total_seconds()
    assert duration >= 0
    stats = state.statistics()
    _assert_aware_iso(stats["created"])
    _assert_aware_iso(stats["started"])
    _assert_aware_iso(stats["finished"])
    assert stats["duration"] is not None


def test_execution_context_serialization_stays_aware():
    ctx = ExecutionContext(request={"q": 1})
    assert ctx.created.tzinfo is not None
    payload = ctx.serialize()
    _assert_aware_iso(payload["created"])


def test_coordinator_state_transitions_stay_aware():
    manager = CoordinatorStateManager()
    assert manager.created.tzinfo is not None
    manager.start()
    manager.wait()
    assert manager.updated.tzinfo is not None
    assert manager.updated >= manager.created  # no TypeError
    for item in manager.history():
        _assert_aware_iso(item["timestamp"])
    stats = manager.statistics()
    _assert_aware_iso(stats["created"])
    _assert_aware_iso(stats["updated"])


def test_coordinator_metrics_report_and_reset_stay_aware():
    metrics = CoordinatorMetrics(kernel=object())
    assert metrics.started.tzinfo is not None
    report = metrics.report()
    _assert_aware_iso(report["timestamp"])
    assert report["uptime_seconds"] >= 0
    metrics.reset()
    assert metrics.started.tzinfo is not None


def test_synchronization_wait_uses_aware_clock():
    manager = SynchronizationManager(kernel=object())
    manager.create_barrier("phase-e", expected=1)
    assert manager.arrive("phase-e") is True
    assert manager.wait("phase-e", timeout=1) is True
    # Timeout path exercises `datetime.now(timezone.utc) - start`.
    manager.create_barrier("never", expected=5)
    assert manager.wait("never", timeout=0.05) is False
    barrier = manager.barriers["never"]
    assert barrier.created.tzinfo is not None


def test_execution_graph_timestamps_are_aware():
    graph = ExecutionGraph()
    graph.add_dependency("b", "a")
    graph.mark_completed("a")
    node = graph.nodes["a"]
    assert node.started is not None and node.started.tzinfo is not None
    assert node.finished is not None and node.finished.tzinfo is not None
    assert node.finished >= node.started  # no TypeError


def test_intelligence_core_timestamps_are_aware():
    core = IntelligenceCore(kernel=object())
    result = core.process({"input": "ping"})
    _assert_aware_iso(result["timestamp"])
    _assert_aware_iso(result["response"]["generated"])


def test_task_manager_timestamps_are_aware():
    manager = TaskManager()
    task_id = manager.create_task("phase-e check")
    task = manager.get(task_id)
    for key in ("created_at", "updated_at"):
        _assert_aware_iso(task[key])
    _assert_aware_iso(task["history"][0]["time"])


def test_timestamp_ordering_and_serialization_roundtrip():
    monitor = RuntimeMonitor()
    monitor.record("first", {})
    monitor.record("second", {})
    stamps = [_assert_aware_iso(e["timestamp"]) for e in monitor.events]
    assert stamps[1] >= stamps[0]
    # JSON-compatible strings survive a serialize/deserialize round trip.
    import json

    blob = json.dumps(monitor.events)
    restored = json.loads(blob)
    assert _assert_aware_iso(restored[0]["timestamp"]) == stamps[0]


def test_no_naive_aware_mismatch_across_components():
    """Regression: mixing any two component timestamps must not raise TypeError."""
    cache = RuntimeCache()
    cache.put("k", "v", ttl=60)
    metrics = RuntimeMetrics()
    state_mgr = CoordinatorStateManager()
    state_mgr.start()
    candidates = [
        cache.cache["k"].created,
        cache.cache["k"].expires,
        metrics.started,
        state_mgr.created,
        state_mgr.updated,
        datetime.now(timezone.utc),
    ]
    for candidate in candidates:
        assert candidate.tzinfo is not None
    ordered = sorted(candidates)
    assert len(ordered) == len(candidates)
    for earlier, later in zip(ordered, ordered[1:]):
        assert (later - earlier).total_seconds() >= 0 or True  # comparison itself must not raise
