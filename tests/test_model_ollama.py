"""Model layer: real Ollama integration, routing, structured output.

All transport tests are hermetic (monkeypatched urlopen / adapters) —
no live server required. A separate live test at the bottom runs only
when HERCULE_LIVE_OLLAMA=1 with a reachable server.
"""
import io
import json
import os
import socket
import urllib.error

import pytest

import models.ollama.client as ollama_client_mod
from models.model_manager import ModelManager
from models.ollama.client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)
from models.structured import parse_structured_intent


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        self._payload = payload.encode("utf-8") if isinstance(payload, str) else payload
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_urlopen_factory(routes, captured=None):
    """routes: {(method, path): FakeHTTPResponse | Exception}."""
    def fake_urlopen(request, timeout=None):
        if isinstance(request, str):
            url, method, body = request, "GET", ""
        else:
            url, method = request.full_url, request.get_method()
            body = request.data.decode("utf-8") if request.data else ""
        if captured is not None:
            captured.append({"url": url, "timeout": timeout, "body": body})
        path = url.split("11434")[-1]
        key = (method, path)
        if key not in routes:
            raise AssertionError(f"unexpected request {key}")
        outcome = routes[key]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return fake_urlopen


TAGS = {"models": [
    {"name": "test-llm:3b", "size": 2000,
     "details": {"parameter_size": "3B", "context_length": 8192},
     "capabilities": ["completion", "thinking"]},
    {"name": "test-small:1b", "size": 500,
     "details": {"parameter_size": "1B", "context_length": 4096},
     "capabilities": ["completion"]},
]}


def test_provider_discovery_lists_adapters():
    manager = ModelManager(config={"allow_mock_fallback": True})
    report = manager.discover_models()
    assert set(report["providers"]) >= {"mock", "ollama"}
    assert "default_model" in report


def test_model_discovery_parses_tags(monkeypatch):
    monkeypatch.setattr(
        ollama_client_mod.urllib.request, "urlopen",
        fake_urlopen_factory({("GET", "/api/tags"): FakeHTTPResponse(TAGS)}))
    client = OllamaClient()
    assert client.list_models() == ["test-llm:3b", "test-small:1b"]
    assert client.exists("test-llm:3b") is True
    assert client.exists("ghost:99b") is False


def test_ollama_connection_failure_is_structured(monkeypatch):
    monkeypatch.setattr(
        ollama_client_mod.urllib.request, "urlopen",
        fake_urlopen_factory({("GET", "/api/tags"): urllib.error.URLError("refused")}))
    client = OllamaClient()
    with pytest.raises(OllamaConnectionError):
        client.list_models()


def test_missing_model_raises_not_found(monkeypatch):
    err = urllib.error.HTTPError("http://x/api/chat", 404, "Not Found", {}, io.BytesIO(b""))
    monkeypatch.setattr(
        ollama_client_mod.urllib.request, "urlopen",
        fake_urlopen_factory({("POST", "/api/chat"): err}))
    client = OllamaClient()
    with pytest.raises(OllamaModelNotFoundError):
        client.chat("ghost:99b", "hi")


def test_successful_generation(monkeypatch):
    captured = []
    monkeypatch.setattr(
        ollama_client_mod.urllib.request, "urlopen",
        fake_urlopen_factory({
            ("POST", "/api/chat"): FakeHTTPResponse(
                {"message": {"role": "assistant", "content": "hello there"}}),
        }, captured=captured))
    client = OllamaClient()
    assert client.chat("test-llm:3b", "hi", timeout_s=30) == "hello there"
    body = json.loads(captured[0]["body"])
    assert body["model"] == "test-llm:3b" and body["stream"] is False
    assert captured[0]["timeout"] == 30


def test_timeout_surfaces_structured(monkeypatch):
    monkeypatch.setattr(
        ollama_client_mod.urllib.request, "urlopen",
        fake_urlopen_factory({("POST", "/api/chat"): socket.timeout("timed out")}))
    client = OllamaClient()
    with pytest.raises(OllamaTimeoutError):
        client.chat("test-llm:3b", "hi")


@pytest.mark.parametrize("payload", [
    {"no_message": True},
    {"message": {"role": "assistant", "content": "   "}},
    {"message": "not-an-object"},
    "not json at all{{{",
])
def test_malformed_model_response_rejected(monkeypatch, payload):
    monkeypatch.setattr(
        ollama_client_mod.urllib.request, "urlopen",
        fake_urlopen_factory({("POST", "/api/chat"): FakeHTTPResponse(payload)}))
    client = OllamaClient()
    with pytest.raises(OllamaResponseError):
        client.chat("test-llm:3b", "hi")


def test_structured_output_valid():
    ok, clean, error = parse_structured_intent(json.dumps({
        "intent": "read_file", "goal": "Read this file",
        "reasoning_summary": "need file contents",
        "capabilities": ["file_read"], "arguments": {"path": "a.txt"}}))
    assert ok and not error
    assert clean["capabilities"] == ["FILE_READ"]
    assert clean["arguments"] == {"path": "a.txt"}


def test_structured_output_fenced():
    ok, clean, _ = parse_structured_intent(
        'Here you go:\n```json\n{"intent": "x", "goal": "y", '
        '"reasoning_summary": "z", "capabilities": ["MATH"], "arguments": {}}\n```')
    assert ok and clean["capabilities"] == ["MATH"]


@pytest.mark.parametrize("text", [
    "",
    "just some prose, no json",
    json.dumps({"intent": "x"}),
    json.dumps({"intent": "x", "goal": "y", "reasoning_summary": "z",
                "capabilities": ["MIND_CONTROL"], "arguments": {}}),
    json.dumps({"intent": "x", "goal": "y", "reasoning_summary": "z",
                "capabilities": "MATH", "arguments": {}}),
    json.dumps({"intent": "x", "goal": "y", "reasoning_summary": "z",
                "capabilities": ["MATH"], "arguments": {"nested": {"evil": 1}}}),
    json.dumps({"intent": "", "goal": "y", "reasoning_summary": "z",
                "capabilities": ["MATH"], "arguments": {}}),
])
def test_structured_output_invalid_fails_safely(text):
    ok, clean, error = parse_structured_intent(text)
    assert not ok and clean == {} and error


def test_model_routing_by_purpose(monkeypatch):
    from models.router.model_router import ModelRouter
    router = ModelRouter()
    ollama = router.adapters["ollama"]
    monkeypatch.setattr(ollama, "discover_models",
                        lambda: ["test-llm:3b", "test-small:1b"])
    monkeypatch.setattr(ollama.client, "model_details", lambda: TAGS["models"])
    # Seed the registry the way ModelManager would.
    from models.registry.registry import ModelInfo
    for name in ("test-llm:3b", "test-small:1b"):
        if router.registry.get(name) is None:
            router.registry.register(ModelInfo(
                name=name, provider="ollama", context_length=8192,
                capabilities=["chat"], priority=10, enabled=True, adapter_name="ollama"))
    assert router.route_for_purpose("reasoning", default_model="test-small:1b")[0] == "test-llm:3b"
    assert router.route_for_purpose("light", default_model="test-llm:3b")[0] == "test-small:1b"
    assert router.route_for_purpose("conversation", default_model="test-small:1b")[0] == "test-small:1b"


def test_mock_excluded_from_production_fallback(monkeypatch, tmp_path):
    from models.adapters.ollama_adapter import OllamaAdapter
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "")
    # Isolate from ambient user data: a real GGUF on this machine is a
    # legitimate production fallback, but this test proves the MOCK is
    # never silently used (keep that assertion hermetic).
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(OllamaAdapter, "health",
                        lambda self: {"status": "unavailable", "available": False,
                                      "reason": "down"})
    manager = ModelManager(default_model="ghost-ollama-model")
    result = manager.generate_detailed("hi")
    assert result["status"] == "failed"
    assert "MOCK ANSWER" not in result["error"]
    assert all(a["provider"] != "mock" for a in result["attempts"])
    assert result["attempts"]  # attempts were genuinely made/recorded


def test_mock_explicit_selection_still_works():
    manager = ModelManager(default_model="mock")
    assert "MOCK ANSWER" in manager.generate("test prompt")


def test_load_unknown_model_raises(monkeypatch):
    from models.adapters.ollama_adapter import OllamaAdapter
    monkeypatch.setattr(OllamaAdapter, "discover_models", lambda self: [])
    manager = ModelManager(default_model="mock")
    with pytest.raises(RuntimeError, match="not found"):
        manager.load_model("ghost-model:99b")


def test_default_resolves_to_installed(monkeypatch):
    from models.adapters.ollama_adapter import OllamaAdapter
    monkeypatch.setattr(OllamaAdapter, "discover_models",
                        lambda self: ["test-llm:3b"])
    monkeypatch.setattr(OllamaAdapter.client if hasattr(OllamaAdapter, "client") else OllamaAdapter,
                        "model_details", lambda self: [], raising=False)
    manager = ModelManager(default_model="llama3")
    assert manager.default_model == "test-llm:3b"


@pytest.mark.skipif(os.environ.get("HERCULE_LIVE_OLLAMA") != "1",
                    reason="live Ollama test (set HERCULE_LIVE_OLLAMA=1)")
def test_live_ollama_generation():
    manager = ModelManager()
    assert manager.installed_ollama_models(), "no models on live server"
    result = manager.generate_detailed("Reply with exactly: LIVE-OK", timeout_s=120)
    assert result["status"] == "success", result
    assert result["provider"] == "ollama"
    assert "LIVE-OK" in result["response"]
