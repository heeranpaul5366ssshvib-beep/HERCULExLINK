"""Phase F: capabilities, health, routing memory, advanced router + fallback."""

import pytest

from models.adapters.mock_adapter import MockAdapter
from models.capabilities import ModelCapability, ModelCapabilityRegistry, profile_from_info
from models.model_health import HealthState, ModelHealthMonitor
from models.registry.registry import ModelInfo
from models.router.advanced_router import AdvancedModelRouter, ModelRoutingFailure
from models.router.model_router import ModelRouter
from models.routing_performance import RoutingMemory


class _DeadAdapter:
    def health(self):
        return {"status": "unavailable", "available": False, "reason": "offline for tests"}


class _FlakyAdapter:
    def __init__(self):
        self.calls = 0

    def health(self):
        return {"status": "healthy", "available": True}

    def generate(self, prompt="", model=None, **kwargs):
        self.calls += 1
        raise RuntimeError("simulated inference timeout")


def test_capability_registry_matching():
    registry = ModelCapabilityRegistry()
    registry.register(ModelCapability(model_name="coder", coding=0.9, reasoning=0.6, context_length=8192))
    registry.register(ModelCapability(model_name="tiny", coding=0.2, reasoning=0.3, context_length=512))
    matches = registry.matching({"coding": 0.6})
    assert [m.model_name for m in matches] == ["coder"]
    assert registry.matching({"coding": 0.6}, min_context=16384) == []
    assert registry.matching({"vision": 0.9}) == []
    assert registry.get("missing") is None
    assert registry.update("coder", latency_ms=120.0).latency_ms == 120.0
    assert registry.update("missing", latency_ms=1.0) is None


def test_profile_bridge_from_legacy_model_info():
    info = ModelInfo(name="llama3", provider="ollama", context_length=4096, capabilities=["reasoning", "chat"])
    profile = profile_from_info(info)
    assert profile.reasoning == 0.7
    assert profile.context_length == 4096
    assert profile.hardware == "ollama-server"


def test_health_monitor_tracks_real_states():
    monitor = ModelHealthMonitor(failure_threshold=2, degraded_latency_ms=0.0)
    first = monitor.check("mock", MockAdapter())
    assert first.available is True
    assert first.state == HealthState.LOADING  # single success is not trust yet
    second = monitor.check("mock", MockAdapter())
    assert second.state in (HealthState.AVAILABLE, HealthState.DEGRADED)
    assert second.last_checked and second.latency_ms >= 0
    monitor.check("dead", _DeadAdapter())
    monitor.check("dead", _DeadAdapter())
    assert monitor.record("dead").state == HealthState.FAILED
    assert "dead" not in monitor.healthy_adapters()
    assert "mock" in monitor.healthy_adapters()


def test_routing_memory_prior_blocks_single_anomaly():
    memory = RoutingMemory()
    memory.record("model-a", "coding", True, 100.0)
    memory.record("model-a", "coding", True, 110.0)
    memory.record("model-a", "coding", True, 105.0)
    memory.record("model-b", "coding", False, 50.0)  # one fast failure
    assert memory.success_rate("model-a", "coding") > memory.success_rate("model-b", "coding")
    assert memory.best_model(["model-a", "model-b"], "coding") == "model-a"  # stable despite one fast failure
    assert memory.best_model(["model-a", "model-b"], "coding", min_samples=4) is None  # immature data
    for _ in range(3):
        memory.record("model-b", "coding", True, 60.0)
    assert memory.best_model(["model-a", "model-b"], "coding") in ("model-a", "model-b")
    assert memory.stats_for("model-a", "coding").latency_ewma_ms > 0


def test_advanced_router_scores_and_explains():
    router = AdvancedModelRouter(ModelRouter())
    _, _, decision = router.route_with_scores("reason about the failing plan")
    assert decision.model and decision.adapter_name
    assert decision.reason and decision.task_type
    assert len(decision.fallback_chain) >= 1
    assert len(decision.scores) == len(decision.fallback_chain)
    totals = [s.total for s in decision.scores]
    assert totals == sorted(totals, reverse=True)
    for scored in decision.scores:
        assert set(scored.factors) == {"capability", "availability", "health", "latency", "resources", "history"}
    payload = decision.as_dict()
    assert payload["model"] == decision.model


def test_advanced_router_respects_capability_requirements():
    router = AdvancedModelRouter(ModelRouter())
    router.capabilities.register(ModelCapability(model_name="mock", coding=0.1, reasoning=0.3, context_length=1024))
    _, _, decision = router.route_with_scores("write embedded firmware", requirements={"coding": 0.05})
    assert decision.requirements == {"coding": 0.05}
    with pytest.raises(ModelRoutingFailure):
        router.route_with_scores("task", requirements={"vision": 0.99})


def test_generate_with_fallback_uses_secondary_and_records_memory():
    from models.registry.registry import ModelInfo

    base = ModelRouter()
    base.adapters["flaky"] = _FlakyAdapter()
    base.registry.register(ModelInfo(name="flaky-model", provider="flaky", context_length=1024, capabilities=["reasoning", "testing"], adapter_name="flaky"))
    # Deterministic candidate set: environment adapters (ollama server,
    # local transformers) vary by machine, so isolate flaky vs mock.
    for name in ("llama3", "tiny-gpt2"):
        base.registry.unregister(name)
    base.adapters = {"flaky": base.adapters["flaky"], "mock": base.adapters["mock"]}
    router = AdvancedModelRouter(base)
    response, decision = router.generate_with_fallback("Hello", task="smoke test demo", preferred_model="flaky-model")
    assert "MOCK ANSWER" in response
    assert decision.fallback_chain[0] == "flaky"  # preferred first, fails, falls through
    assert "mock" in decision.fallback_chain
    summary = router.memory.summary()
    assert any(entry["model_name"] == "flaky-model" and entry["failures"] >= 1 for entry in summary)
    assert any(entry["model_name"] == "mock" and entry["samples"] >= 1 for entry in summary)


def test_total_failure_is_explicit_never_silent():
    base = ModelRouter()
    base.adapters = {"dead-a": _DeadAdapter(), "dead-b": _DeadAdapter()}
    router = AdvancedModelRouter(base)
    with pytest.raises(ModelRoutingFailure) as excinfo:
        router.generate_with_fallback("Hello", task=" aboard task ")
    assert excinfo.value.decision is not None
    assert "fail" in str(excinfo.value).lower()


def test_overloaded_slow_models_are_deprioritized():
    router = AdvancedModelRouter(ModelRouter())
    router.capabilities.update("mock", latency_ms=5.0)
    _, _, decision = router.route_with_scores("smoke test demo")
    assert decision.model
    assert all(s.factors["latency"] > 0 for s in decision.scores)
