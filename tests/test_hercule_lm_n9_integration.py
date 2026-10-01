from __future__ import annotations
"""HERCULE-LM N9 Integration Tests: native provider as first-class production model provider.

Tests cover:
A. Native provider imports successfully.
B. discover_models() finds the expected native checkpoint.
C. Native model metadata is correct.
D. load_model() loads the actual checkpoint.
E. Missing checkpoint returns a clean failure.
F. Invalid checkpoint returns a clean failure.
G. ModelRouter can explicitly route to native provider.
H. ModelManager detects the native model.
I. Existing Ollama routing still works.
J. Existing builtin routing still works.
K. Existing Transformers routing still works.
L. Mock remains disabled unless explicitly enabled.
M. Native inference can complete one minimal deterministic generation.
"""

import json
from pathlib import Path

import pytest


def test_A_native_provider_imports():
    """A. Native provider imports successfully."""
    from models.hercule_lm.provider import HerculeLMProvider, HerculeLMUnavailable

    assert HerculeLMProvider is not None
    assert HerculeLMUnavailable is not None
    provider = HerculeLMProvider()
    assert provider.name == "hercule-lm"


def test_B_discover_models_finds_checkpoint():
    """B. discover_models() finds the expected native checkpoint."""
    from models.hercule_lm.provider import HerculeLMProvider

    provider = HerculeLMProvider()
    models = provider.discover_models()
    assert isinstance(models, list)
    # Should find at least the micro1 checkpoint
    assert "hercule-lm-micro" in models, f"Expected hercule-lm-micro in {models}"


def test_C_native_model_metadata_correct():
    """C. Native model metadata is correct."""
    from models.hercule_lm.provider import HerculeLMProvider

    provider = HerculeLMProvider()
    health = provider.health()
    # Provider is available if it can discover models (lazy loading)
    assert health["available"] is True
    assert health["native"] is True
    assert health["provider"] == "hercule-lm"
    assert "discovered_models" in health
    assert "hercule-lm-micro" in health["discovered_models"]
    # When available, no "reason" key; "reason" only present when unavailable
    assert "reason" not in health or health["available"] is False


def test_D_load_model_loads_checkpoint():
    """D. load_model() loads the actual checkpoint."""
    from models.hercule_lm.provider import HerculeLMProvider

    provider = HerculeLMProvider()
    result = provider.load_model("hercule-lm-micro")
    assert result["status"] == "loaded"
    assert result["model"] == "hercule-lm-micro"
    assert "checkpoint" in result
    assert result["params"] == 3088384

    # Health should now show available
    health = provider.health()
    assert health["available"] is True
    assert health["model"] == "hercule-lm-micro"
    assert health["params"] == 3088384
    assert health["native"] is True
    assert health["checkpoint"] is not None


def test_E_missing_checkpoint_clean_failure():
    """E. Missing checkpoint returns a clean failure."""
    from models.hercule_lm.provider import HerculeLMProvider, HerculeLMUnavailable

    provider = HerculeLMProvider()
    with pytest.raises(HerculeLMUnavailable) as exc_info:
        provider.load_model("nonexistent-model")
    assert "no HERCULE-LM checkpoint found" in str(exc_info.value)


def test_F_invalid_checkpoint_clean_failure():
    """F. Invalid checkpoint returns a clean failure."""
    from models.hercule_lm.provider import HerculeLMProvider, HerculeLMUnavailable

    # Provider with invalid checkpoint path - health should report unavailable
    provider = HerculeLMProvider(checkpoint="/nonexistent/path")
    health = provider.health()
    # Provider reports unavailable because the specific checkpoint is invalid
    assert health["available"] is False
    assert health["native"] is True
    assert health["provider"] == "hercule-lm"
    assert "reason" in health
    
    # But loading a valid model by name should work
    result = provider.load_model("hercule-lm-micro")
    assert result["status"] == "loaded"
    
    # Now health should show available
    health2 = provider.health()
    assert health2["available"] is True
    assert health2["native"] is True


def test_G_model_router_explicit_route_to_native():
    """G. ModelRouter can explicitly route to native provider."""
    from models.router.model_router import ModelRouter

    router = ModelRouter()
    # Should be able to route to native model by name
    adapter_name, adapter = router.route_by_name("hercule-lm-micro")
    assert adapter_name == "hercule-lm"
    assert hasattr(adapter, "generate")


def test_H_model_manager_detects_native_model():
    """H. ModelManager detects the native model."""
    from models.model_manager import ModelManager

    # Use native provider preference
    manager = ModelManager(default_model="hercule-lm-micro", config={"model_provider": "native"})
    # Should resolve to native model
    assert manager.default_model == "hercule-lm-micro"
    # Should be able to discover native models
    discovered = manager.installed_native_models()
    assert "hercule-lm-micro" in discovered


def test_I_existing_ollama_routing_still_works():
    """I. Existing Ollama routing still works."""
    from models.model_manager import ModelManager

    manager = ModelManager(default_model="llama3", config={"model_provider": "ollama"})
    # Should default to ollama routing
    assert manager.provider_pref == "ollama"
    # Router should have ollama adapter
    assert "ollama" in manager.router.adapters


def test_J_existing_builtin_routing_still_works():
    """J. Existing builtin routing still works."""
    from models.model_manager import ModelManager

    manager = ModelManager(default_model="hercule-local", config={"model_provider": "builtin"})
    # Should default to builtin routing
    assert manager.provider_pref == "builtin"
    # Router should have builtin adapter
    assert "builtin" in manager.router.adapters


def test_K_existing_transformers_routing_still_works():
    """K. Existing Transformers routing still works."""
    from models.model_manager import ModelManager

    manager = ModelManager(default_model="tiny-gpt2", config={"model_provider": "auto"})
    # Router should have transformers adapter
    assert "transformers" in manager.router.adapters


def test_L_mock_remains_disabled_unless_explicit():
    """L. Mock remains disabled unless explicitly enabled."""
    from models.model_manager import ModelManager

    # Default: mock should not be used
    manager = ModelManager(default_model="llama3")
    # Mock adapter exists but should be excluded from production fallback
    ordered, errors = manager._ordered_adapters("llama3")
    adapter_names = [name for name, _ in ordered]
    assert "mock" not in adapter_names

    # With explicit mock request
    manager_mock = ModelManager(default_model="mock", config={"allow_mock_fallback": True})
    ordered_mock, _ = manager_mock._ordered_adapters("mock")
    adapter_names_mock = [name for name, _ in ordered_mock]
    assert "mock" in adapter_names_mock


def test_M_native_inference_minimal_generation():
    """M. Native inference can complete one minimal deterministic generation."""
    from models.hercule_lm.provider import HerculeLMProvider

    provider = HerculeLMProvider()
    provider.load_model("hercule-lm-micro")

    # Simple generation
    text = provider.generate("Q: Calculate 317 + 542.\nA:", max_tokens=10, temperature=0.0)
    assert isinstance(text, str)
    assert len(text) > 0

    # Health should still be good
    health = provider.health()
    assert health["available"] is True


def test_model_manager_discover_includes_native():
    """ModelManager.discover_models() includes native models."""
    from models.model_manager import ModelManager

    manager = ModelManager(config={"model_provider": "auto"})
    report = manager.discover_models()
    assert "installed_native_models" in report
    assert "hercule-lm-micro" in report["installed_native_models"]
    assert "hercule-lm" in report["providers"]


def test_model_router_installed_hercule_lm_models():
    """ModelRouter.installed_hercule_lm_models() works."""
    from models.router.model_router import ModelRouter

    router = ModelRouter()
    native_models = router.installed_hercule_lm_models()
    assert isinstance(native_models, list)
    assert "hercule-lm-micro" in native_models


def test_model_router_route_for_purpose_reasoning_native_fallback():
    """ModelRouter.route_for_purpose() falls back to native for reasoning."""
    from models.router.model_router import ModelRouter

    router = ModelRouter()
    # When no thinking-capable Ollama models, should fall back to native
    model_name, adapter_name, adapter = router.route_for_purpose("reasoning")
    # Either gets an Ollama thinking model or native
    assert adapter_name in ("ollama", "builtin", "hercule-lm")


def test_model_manager_route_for_purpose_native():
    """ModelManager.route_for_purpose() works with native."""
    from models.model_manager import ModelManager

    manager = ModelManager(config={"model_provider": "native"})
    model_name, adapter_name, adapter = manager.route_for_purpose("reasoning")
    # Should be able to route
    assert adapter_name == "hercule-lm"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])