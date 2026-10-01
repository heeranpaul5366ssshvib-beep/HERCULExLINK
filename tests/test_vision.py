from __future__ import annotations
"""Vision/perception tests (v1.1, read-only).

Covers: provider discovery, unavailable vision model, image loading,
screenshot capture honesty, structured result validation, OCR result,
malformed vision output, Brain integration, UI snapshot, HUD snapshot,
voice-to-vision routing. Fakes live in this test process only —
production code never fabricates observations. No camera, display, or
vision model is required.
"""

import base64
import os
import struct
import zlib

import pytest

from perception.vision.config import VisionConfig, load_vision_config
from perception.vision.manager import VisionManager, image_dimensions
from perception.vision.provider import (
    OllamaVisionProvider,
    VisionUnavailable,
    _parse_model_json,
    get_vision_provider,
)
from perception.vision.result import validate_observation


def _png_1x1() -> bytes:
    def chunk(ctype: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + ctype + payload
                + struct.pack(">I", zlib.crc32(ctype + payload) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\x00\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeOllamaClient:
    def __init__(self, details):
        self._details = details

    def model_details(self):
        return list(self._details)

    def list_models(self):
        return [d["name"] for d in self._details]


def _provider_with(models, **kwargs):
    provider = OllamaVisionProvider(**kwargs)
    fake = FakeOllamaClient(models)
    provider._client = lambda: fake  # type: ignore[assignment]
    provider._probe = None
    return provider


VISION_DETAILS = [
    {"name": "moondream:latest", "details": {"capabilities": ["vision"]}},
    {"name": "llama3.2:3b", "details": {"capabilities": ["completion"]}},
]


# --------------------------------------------------
# 1. provider discovery
# --------------------------------------------------
def test_1_provider_discovery_finds_local_vision_models():
    provider = _provider_with(VISION_DETAILS)
    assert provider.vision_models() == ["moondream:latest"]
    probe = provider.available()
    assert probe["available"] is True
    assert probe["model"] == "moondream:latest"
    with pytest.raises(ValueError, match="unknown vision provider"):
        get_vision_provider("cloud-magic")


def test_1b_name_fragment_match_without_capabilities():
    provider = _provider_with([{"name": "llava:7b"}])
    assert provider.vision_models() == ["llava:7b"]


# --------------------------------------------------
# 2. unavailable vision model (honest, never fabricated)
# --------------------------------------------------
def test_2_no_vision_model_reports_unavailable():
    provider = _provider_with([{"name": "llama3.2:3b",
                                "details": {"capabilities": ["completion"]}}])
    probe = provider.available()
    assert probe["available"] is False
    assert "VISION UNAVAILABLE" in probe["reason"]
    with pytest.raises(VisionUnavailable):
        provider.describe(base64.b64encode(b"x").decode(), "image/png", "hi")
    manager = VisionManager(provider=provider)
    assert manager.availability()["available"] is False


# --------------------------------------------------
# 3. image loading (workspace sandbox + bounds)
# --------------------------------------------------
def test_3_image_loading_and_sandbox(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ok.png").write_bytes(_png_1x1())
    manager = VisionManager()
    data, mime, width, height = manager.load_image_file("ok.png")
    assert mime == "image/png" and (width, height) == (1, 1)
    assert data == _png_1x1()
    with pytest.raises(ValueError, match="image not found"):
        manager.load_image_file("missing.png")
    with pytest.raises(ValueError, match="sandbox"):
        manager.load_image_file("../evil.png")
    with pytest.raises(ValueError, match="sandbox"):
        manager.load_image_file("C:\\Windows\\x.png")
    w, h, mime = image_dimensions(_png_1x1())
    assert (w, h, mime) == (1, 1, "image/png")


# --------------------------------------------------
# 4. screenshot capture (honest when uncapturable)
# --------------------------------------------------
def test_4_screenshot_capture_honest():
    manager = VisionManager()
    try:
        data, mime, width, height = manager.capture_screenshot()
    except VisionUnavailable as exc:
        assert "screenshot" in str(exc).lower()
    else:
        assert len(data) > 0 and mime == "image/png"
        assert width > 0 and height > 0


# --------------------------------------------------
# 5. structured result validation
# --------------------------------------------------
def test_5_structured_result_validation():
    good = {"description": "a test screen", "detected_text": ["OK"],
            "regions": [{"label": "button", "x": 0.1, "y": 0.2,
                         "width": 0.3, "height": 0.1, "confidence": 0.9}],
            "objects": ["button"], "confidence": 0.9, "source": "screenshot",
            "model": "m", "width": 800, "height": 600}
    obs = validate_observation(good)
    assert obs.description == "a test screen"
    assert obs.as_dict()["confidence"] == 0.9
    with pytest.raises(ValueError, match="missing description"):
        validate_observation({**good, "description": "  "})
    with pytest.raises(ValueError, match="confidence"):
        validate_observation({**good, "confidence": 2.0})
    with pytest.raises(ValueError, match="region"):
        validate_observation({**good, "regions": [{"label": "x", "confidence": 9}]})
    with pytest.raises(ValueError, match="not a mapping"):
        validate_observation("nope")  # type: ignore[arg-type]


# --------------------------------------------------
# 6. OCR result (separated from visual reasoning)
# --------------------------------------------------
def test_6_ocr_separated_and_honest():
    manager = VisionManager()
    result = manager.extract_text(_png_1x1())
    assert set(result) >= {"available", "text"}
    if result["available"]:
        assert isinstance(result["text"], list)
    else:
        assert "reason" in result and result["text"] == []


# --------------------------------------------------
# 7. malformed vision output (never reaches execution)
# --------------------------------------------------
def test_7_malformed_vision_output_rejected():
    with pytest.raises(ValueError, match="empty"):
        _parse_model_json("   ")
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_model_json('{"description": broken')
    wrapped = _parse_model_json("a plain description")
    assert wrapped["description"] == "a plain description"
    assert wrapped["regions"] == [] and wrapped["objects"] == []


# --------------------------------------------------
# 8. Brain integration (structured observation, no CoT)
# --------------------------------------------------
def test_8_brain_integration(monkeypatch):
    os.environ.setdefault("HERCULE_TASK_STORE", ":memory:")
    os.environ.setdefault("HERCULE_ALLOW_MOCK", "1")
    os.environ.setdefault("HERCULE_DEFAULT_MODEL", "mock")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    canned = {"description": "test screen", "detected_text": [],
              "regions": [], "objects": [], "confidence": 0.8,
              "source": "screenshot", "model": "fake", "width": 10,
              "height": 10, "ocr_available": False}

    def fake_visual(source="screenshot", path="", prompt=""):
        return dict(canned)

    monkeypatch.setattr(services["perception"], "analyze_visual", fake_visual)
    outcome = brain.observe_visual("screenshot")
    assert outcome["status"] == "observed"
    assert outcome["observation"]["description"] == "test screen"
    assert "test screen" in outcome["response"]
    assert "chain" not in str(outcome).lower()

    def boom(source="screenshot", path="", prompt=""):
        raise VisionUnavailable("VISION UNAVAILABLE: no vision model")

    monkeypatch.setattr(services["perception"], "analyze_visual", boom)
    with pytest.raises(VisionUnavailable):
        brain.observe_visual("screenshot")


# --------------------------------------------------
# 9. UI snapshot (display only; skipped headless)
# --------------------------------------------------
def test_9_ui_snapshot_when_display_available():
    pytest.importorskip("tkinter")
    import tkinter as tk
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
    except Exception as exc:
        pytest.skip(f"no display available: {exc}")
    os.environ.setdefault("HERCULE_DEFAULT_MODEL", "mock")
    os.environ.setdefault("HERCULE_ALLOW_MOCK", "1")
    os.environ.setdefault("HERCULE_TASK_STORE", ":memory:")
    from interface.app_controller import HerculeAppController
    from interface.desktop_app import HerculeDesktopApp
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    root = tk.Tk()
    root.withdraw()
    try:
        app = HerculeDesktopApp(controller, root=root)
        app._refresh()
        assert "vision" in app.vision_var.get().lower()
        assert app.vision_text_var.get().startswith("see:")
    finally:
        root.destroy()


# --------------------------------------------------
# 10. HUD snapshot (real state only)
# --------------------------------------------------
def test_10_hud_snapshot_keys():
    os.environ.setdefault("HERCULE_TASK_STORE", ":memory:")
    os.environ.setdefault("HERCULE_ALLOW_MOCK", "1")
    os.environ.setdefault("HERCULE_DEFAULT_MODEL", "mock")
    from interface.app_controller import HerculeAppController
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    snap = controller.snapshot()
    assert set(snap) >= {"vision", "consciousness", "model", "task"}
    vision = snap["vision"]
    assert set(vision) >= {"state", "ready", "analyzing", "has_result",
                           "description", "confidence", "source", "model",
                           "error", "available"}
    assert vision["state"] in ("READY", "ANALYZING", "RESULT", "UNAVAILABLE")
    assert vision["has_result"] is False  # nothing analyzed yet: honest


# --------------------------------------------------
# 11. voice-to-vision routing (same pipeline, no mic)
# --------------------------------------------------
def test_11_voice_transcript_routes_to_vision_pipeline():
    from cognition.capabilities.inference import infer_capabilities
    from voice.config import VoiceConfig
    from voice.controller import VoiceController

    caps = infer_capabilities("Analyze this screen (screenshot)")
    assert "VISION_ANALYSIS" in [c.value for c in caps]

    class FakeApp:
        def __init__(self):
            self.submitted = []
            from brain.consciousness import Consciousness
            self.brain = type("Brain", (), {"consciousness": Consciousness()})()

        def submit(self, text):
            self.submitted.append(text)
            return {"kind": "GOAL", "status": "completed", "response": "saw it"}

        def format_response(self, result):
            return result.get("response", "")

    app = FakeApp()
    voice = VoiceController(app, VoiceConfig(enabled=True))
    text = voice.submit_transcript("What does this image show?")
    assert app.submitted == ["What does this image show?"]
    assert text == "saw it"


def test_vision_config_defaults_local_only():
    config = load_vision_config(env={})
    assert config.timeout_s == 60.0
    assert config.ocr_enabled is True
    blob = str(config.as_dict())
    assert "key" not in blob.lower() and "token" not in blob.lower()
    assert isinstance(VisionConfig().as_dict(), dict)
