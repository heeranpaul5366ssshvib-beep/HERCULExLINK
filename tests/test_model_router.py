from models.router.model_router import ModelRouter


def test_router_prefers_healthy_backend():
    router = ModelRouter({"preferred_adapter": "mock", "fallback_adapters": ["mock", "ollama", "transformers"]})
    adapter = router.select_adapter_for_task("Run a simple smoke test")
    assert adapter is not None


def test_router_handles_unavailable_backend():
    router = ModelRouter({"preferred_adapter": "ollama", "fallback_adapters": ["mock"]})
    adapter = router.select_adapter_for_task("Debug this issue")
    assert adapter is not None


def test_router_health_report_contains_adapters():
    router = ModelRouter()
    status = router.health()
    assert isinstance(status, dict)
    assert "mock" in status


def test_route_by_name_raises_for_missing_model():
    router = ModelRouter()
    try:
        router.route_by_name("missing-model")
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
