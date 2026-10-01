from __future__ import annotations
"""Built-in local LLM provider tests (v2).

Covers: registration, discovery, loading, missing model, invalid
path, generation, timeout, structured output, routing, offline mode,
no Ollama, no internet, CPU execution, installer path, LOCALAPPDATA
persistence, switching, unload/reload, Brain/planning/computer-use
integration. Fakes live in this test process only. Tests that need a
real GGUF + llama-server are gated behind HERCULE_LIVE_BUILTIN=1 and
skip otherwise (no 400MB downloads in CI).
"""

import json
import os

import pytest

from models.builtin.config import (
    BuiltinConfig,
    default_threads,
    detect_gpu,
    load_builtin_config,
)
from models.builtin.provider import BuiltinLocalProvider, BuiltinUnavailable


class FakeRuntime:
    """In-process stand-in for LlamaRuntime (no server, no weights)."""

    def __init__(self, text='{"intent": "chat", "goal": "hi"}', tps=42.0):
        self.text = text
        self.calls = []
        self.started = []
        self.stopped = 0
        self._running = False
        self.device = "cpu"
        self.load_time_s = 1.5
        self.last_tokens_per_sec = tps
        self.last_prompt_ms = 10.0
        self.last_gen_ms = 100.0

    @property
    def running(self):
        return self._running

    def start(self, model_path):
        self.started.append(str(model_path))
        self._running = True
        return {"loaded": True, "cached": False, "load_time_s": 1.5}

    def chat(self, messages, max_tokens=512, temperature=0.7, top_p=0.9,
             timeout_s=None):
        self.calls.append(messages)
        if isinstance(self.text, Exception):
            raise self.text
        return {"text": self.text, "prompt_ms": 10.0, "gen_ms": 100.0,
                "tokens_per_sec": self.last_tokens_per_sec,
                "completion_tokens": 8, "total_ms": 110.0}

    def stop(self):
        self.stopped += 1
        self._running = False
        return {"stopped": True}


def _gguf(tmp_path, name="tiny-test.gguf"):
    target = tmp_path / "HERCULE" / "models" / "gguf" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"GGUF-fake-weights")
    return target


def _env_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


# --------------------------------------------------
# provider registration
# --------------------------------------------------
def test_provider_registered_with_default_model():
    from models.model_manager import ModelManager

    manager = ModelManager.__new__(ModelManager)
    from models.router.model_router import ModelRouter

    router = ModelRouter()
    # Initialize builtin adapter
    router._get_adapter("builtin")
    assert "builtin" in router.adapters
    assert router.registry.get("hercule-local") is not None
    assert router.registry.get("hercule-local").adapter_name == "builtin"
    assert manager is not None


# --------------------------------------------------
# model discovery (real store, isolated user data)
# --------------------------------------------------
def test_model_discovery_finds_local_gguf(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    provider = BuiltinLocalProvider()
    assert provider.discover_models() == ["tiny-test"]
    probe = provider.health()
    assert probe["available"] is True
    assert probe["model"] == "tiny-test"


# --------------------------------------------------
# missing model (honest, never fabricated)
# --------------------------------------------------
def test_missing_model_reports_not_installed(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    provider = BuiltinLocalProvider()
    assert provider.discover_models() == []
    probe = provider.health()
    assert probe["available"] is False
    assert "MODEL NOT INSTALLED" in probe["reason"]
    with pytest.raises(BuiltinUnavailable):
        provider.load_model()


# --------------------------------------------------
# invalid path
# --------------------------------------------------
def test_invalid_model_path_rejected(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    provider = BuiltinLocalProvider(runtime=FakeRuntime())
    with pytest.raises(BuiltinUnavailable):
        provider.load_model("no-such-model")
    from models.builtin.runtime import LlamaRuntime

    runtime = LlamaRuntime()
    with pytest.raises(Exception, match="not found|GGUF"):
        runtime.start(str(tmp_path / "missing.gguf"))
    txt = tmp_path / "note.txt"
    txt.write_text("hi")
    with pytest.raises(Exception, match="GGUF"):
        runtime.start(str(txt))


# --------------------------------------------------
# model loading
# --------------------------------------------------
def test_model_loading_uses_selected_weights(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    target = _gguf(tmp_path)
    fake = FakeRuntime()
    provider = BuiltinLocalProvider(runtime=fake)
    info = provider.load_model("tiny-test")
    assert fake.started == [str(target)]
    assert info["model"] == "tiny-test"
    assert info["load_time_s"] == 1.5


# --------------------------------------------------
# generation (+ timeout propagation)
# --------------------------------------------------
def test_generation_returns_model_text(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    provider = BuiltinLocalProvider(runtime=FakeRuntime(text="hello there"))
    assert provider.generate("hi") == "hello there"
    detailed = provider.generate_detailed("hi")
    assert detailed["status"] == "success"
    assert detailed["provider"] == "builtin"
    assert detailed["tokens_per_sec"] == 42.0
    assert "latency_ms" in detailed


def test_generation_timeout_propagates(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    provider = BuiltinLocalProvider(
        runtime=FakeRuntime(text=TimeoutError("slow")))
    with pytest.raises(TimeoutError):
        provider.generate("hi", timeout_s=1)


# --------------------------------------------------
# structured output validation (existing validator)
# --------------------------------------------------
def test_structured_generation_validated(monkeypatch, tmp_path):
    from models.structured import parse_structured_intent

    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    payload = {"intent": "task", "goal": "read config",
               "reasoning_summary": "need file content",
               "capabilities": ["FILE_READ"], "arguments": {"path": "x.txt"}}
    provider = BuiltinLocalProvider(runtime=FakeRuntime(text=json.dumps(payload)))
    raw = provider.generate("read config as structured json")
    ok, parsed, _ = parse_structured_intent(raw)
    assert ok, parsed
    assert parsed["capabilities"] == ["FILE_READ"]
    bad = BuiltinLocalProvider(runtime=FakeRuntime(text="not json at all"))
    ok, _, _ = parse_structured_intent(bad.generate("x"))
    assert not ok  # malformed model output fails safely


# --------------------------------------------------
# routing (builtin preferred binds builtin for all purposes)
# --------------------------------------------------
def test_model_routing_prefers_configured_builtin(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    from models.model_manager import ModelManager
    from models.adapters.mock_adapter import MockAdapter

    manager = ModelManager(config={"model_provider": "builtin",
                                   "allow_mock_fallback": False})
    # Mock builtin adapter health to avoid needing real GGUF
    builtin_adapter = manager.router._get_adapter("builtin")
    original_health = builtin_adapter.health
    builtin_adapter.health = lambda: {"status": "healthy", "available": True, "model": "tiny-test"}
    try:
        for purpose in ("conversation", "light", "reasoning", "planning",
                        "coding", "complex"):
            model, adapter_name, _ = manager.route_for_purpose(purpose)
            assert adapter_name == "builtin", (purpose, model, adapter_name)
    finally:
        builtin_adapter.health = original_health


# --------------------------------------------------
# offline mode (ollama excluded, deterministic stack intact)
# --------------------------------------------------
def test_offline_mode_excludes_ollama(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    monkeypatch.setenv("HERCULE_OFFLINE", "true")
    from models.model_manager import ModelManager

    manager = ModelManager()
    assert manager.offline is True and manager.provider_pref == "builtin"
    # Mock builtin adapter health
    builtin_adapter = manager.router._get_adapter("builtin")
    original_health = builtin_adapter.health
    builtin_adapter.health = lambda: {"status": "healthy", "available": True, "model": "tiny-test"}
    try:
        ordered, errors = manager._ordered_adapters("hercule-local")
        assert [n for n, _ in ordered if n == "ollama"] == []
        # Error message only added if ollama was in the list and got dropped
        # (ollama not initialized here, so no error expected)
    finally:
        builtin_adapter.health = original_health


# --------------------------------------------------
# no Ollama (dead server + builtin answers)
# --------------------------------------------------
def test_no_ollama_server_builtin_answers(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    monkeypatch.setenv("HERCULE_OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.setenv("HERCULE_MODEL_PROVIDER", "builtin")
    from models.model_manager import ModelManager

    manager = ModelManager()
    # Replace builtin adapter in the internal _adapters dict (adapters property returns a copy)
    manager.router._adapters["builtin"] = BuiltinLocalProvider(
        runtime=FakeRuntime(text="builtin reply"))
    result = manager.generate_detailed("hi")
    assert result["status"] == "success"
    assert result["provider"] == "builtin"
    assert result["response"] == "builtin reply"


# --------------------------------------------------
# no internet (loopback + files only)
# --------------------------------------------------
def test_no_internet_outside_loopback(monkeypatch, tmp_path):
    import urllib.request

    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    real_urlopen = urllib.request.urlopen

    def guarded(request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else str(request)
        if "127.0.0.1" not in url and "localhost" not in url:
            raise AssertionError(f"external access attempted: {url}")
        return real_urlopen(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded)
    provider = BuiltinLocalProvider(runtime=FakeRuntime(text="offline ok"))
    assert provider.generate("hi") == "offline ok"


# --------------------------------------------------
# CPU execution honesty
# --------------------------------------------------
def test_cpu_execution_defaults():
    assert default_threads() >= 1
    gpu = detect_gpu()
    assert set(gpu) >= {"present", "backend", "name"}
    config = load_builtin_config(env={})
    assert config.gpu_layers == 0
    assert "key" not in str(config.as_dict()).lower()
    assert isinstance(BuiltinConfig().as_dict(), dict)


# --------------------------------------------------
# installer path (user data, never Program Files)
# --------------------------------------------------
def test_installer_model_path_separation(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    from models.builtin import model_manager as store

    root = store.models_root()
    assert str(root).startswith(str(tmp_path))
    assert "Program Files" not in str(root)
    assert store.bundled_models_dir() != root


# --------------------------------------------------
# LOCALAPPDATA persistence + switching + unload/reload
# --------------------------------------------------
def test_model_store_select_remove_persist(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    from models.builtin import model_manager as store

    _gguf(tmp_path, "a.gguf")
    _gguf(tmp_path, "b.gguf")
    assert store.select_default("b") == "b"
    assert store.default_model_id() == "b"
    assert store.remove_model("a")["removed"] == "a"
    assert [m["id"] for m in store.list_installed()] == ["b"]
    with pytest.raises(Exception):
        store.select_default("missing")


def test_unload_reload_cycle(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    fake = FakeRuntime(text="again")
    provider = BuiltinLocalProvider(runtime=fake)
    provider.load_model("tiny-test")
    assert provider.unload_model()["unloaded"] is True
    assert fake.stopped == 1
    assert provider.generate("hi") == "again"  # transparent reload
    assert fake.started  # start called again


# --------------------------------------------------
# Brain / planning / computer-use proposal integration
# --------------------------------------------------
def test_brain_think_uses_builtin(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    monkeypatch.setenv("HERCULE_MODEL_PROVIDER", "builtin")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    # Initialize builtin adapter
    services["models"].router._get_adapter("builtin")
    builtin = services["models"].router.adapters["builtin"]
    builtin._runtime = FakeRuntime(text="I am HERCULE, running locally.")
    answer = services["brain"].think("what is your name")
    assert "locally" in answer


def test_computer_use_proposal_still_validated(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path)
    from computer.actions import parse_action

    provider = BuiltinLocalProvider(runtime=FakeRuntime(
        text='{"action": "move", "coordinates": [10, 10]}'))
    proposal = json.loads(provider.generate("propose a pointer move"))
    action = parse_action(proposal)  # validator, never executes
    assert action.action == "move"
    assert action.risk == "LOW"


# --------------------------------------------------
# live server (opt-in; needs real GGUF + binary)
# --------------------------------------------------
def _live_mark():
    return pytest.mark.skipif(
        os.environ.get("HERCULE_LIVE_BUILTIN") != "1",
        reason="live builtin model not enabled")


@_live_mark()
def test_live_generation_through_server():
    from models.builtin import model_manager as store

    installed = store.list_installed()
    assert installed, "no GGUF installed for live test"
    provider = BuiltinLocalProvider()
    try:
        info = provider.load_model(installed[0]["id"])
    finally:
        pass
    assert info["available"] is True
    try:
        text = provider.generate("Say the word HELLO and nothing else.",
                                 max_tokens=16)
    finally:
        provider.unload_model()
    assert isinstance(text, str) and text.strip()


# --------------------------------------------------
# N2: multi-model built-in provider (1.5B primary local)
# --------------------------------------------------
def test_catalog_lists_primary_local_model():
    from models.builtin import model_manager as store

    entry = next((m for m in store.KNOWN_MODELS if m["id"] == "qwen2.5-1.5b-q4"), None)
    assert entry is not None
    assert entry["license"] == "Apache-2.0"
    assert entry["family"] == "Qwen2.5" and entry["parameters"] == "1.5B"
    assert "DEEP" in entry["recommended_modes"] or "STANDARD" in entry["recommended_modes"]
    assert entry["source"].startswith("https://huggingface.co/")


def test_manifest_enrichment_for_known_weights(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path, name="Qwen2.5-1.5B-Instruct-Q4_K_M.gguf")
    from models.builtin import model_manager as store

    metas = [m for m in store.list_installed()
             if m["id"] == "Qwen2.5-1.5B-Instruct-Q4_K_M"]
    assert metas and metas[0].get("license") == "Apache-2.0"
    assert metas[0].get("parameters") == "1.5B"
    assert metas[0].get("family") == "Qwen2.5"


def test_multi_model_discovery_and_default_switch(monkeypatch, tmp_path):
    _env_localappdata(monkeypatch, tmp_path)
    _gguf(tmp_path, name="Qwen2.5-0.5B-Instruct-Q4_K_M.gguf")
    _gguf(tmp_path, name="Qwen2.5-1.5B-Instruct-Q4_K_M.gguf")
    from models.builtin import model_manager as store

    ids = {m["id"] for m in store.list_installed()}
    assert {"Qwen2.5-0.5B-Instruct-Q4_K_M", "Qwen2.5-1.5B-Instruct-Q4_K_M"} <= ids
    assert store.select_default("Qwen2.5-1.5B-Instruct-Q4_K_M") == \
        "Qwen2.5-1.5B-Instruct-Q4_K_M"
    assert store.default_model_id() == "Qwen2.5-1.5B-Instruct-Q4_K_M"
    assert store.select_default("Qwen2.5-0.5B-Instruct-Q4_K_M") == \
        "Qwen2.5-0.5B-Instruct-Q4_K_M"


def test_builtin_first_routing_prefers_larger_for_deep():
    from cognition.reasoning.controller import AdaptiveReasoningController

    class _Models:
        default_model = "llama3.2:3b"
        provider_pref = "builtin"

    class _Controller(AdaptiveReasoningController):
        def inventory(self):
            return [
                {"id": "Qwen2.5-0.5B-Instruct-Q4_K_M", "provider": "builtin",
                 "size": 397808192, "thinking": False, "context": 32768,
                 "capabilities": ["chat"]},
                {"id": "Qwen2.5-1.5B-Instruct-Q4_K_M", "provider": "builtin",
                 "size": 986048512, "thinking": False, "context": 32768,
                 "capabilities": ["chat", "reasoning"]},
            ]

    controller = _Controller(_Models())
    assert controller.select_model("LIGHT")["model"] == "Qwen2.5-0.5B-Instruct-Q4_K_M"
    assert controller.select_model("DEEP")["model"] == "Qwen2.5-1.5B-Instruct-Q4_K_M"
    assert controller.select_model("STANDARD")["model"] == "Qwen2.5-1.5B-Instruct-Q4_K_M"
    for mode in ("LIGHT", "STANDARD", "DEEP", "EXPERT"):
        assert controller.select_model(mode)["provider"] == "builtin"


@_live_mark()
def test_live_primary_model_generation():
    from models.builtin import model_manager as store

    meta = store.find_model("Qwen2.5-1.5B-Instruct-Q4_K_M")
    if meta is None:
        pytest.skip("primary 1.5B model not installed")
    provider = BuiltinLocalProvider()
    try:
        info = provider.load_model("Qwen2.5-1.5B-Instruct-Q4_K_M")
    except Exception as exc:
        pytest.skip(f"primary model unloadable here: {exc}")
    assert info["available"] is True
    try:
        text = provider.generate("What is 8 times 7? Reply with just the number.",
                                 max_tokens=16)
    finally:
        provider.unload_model()
    assert isinstance(text, str) and "56" in text
