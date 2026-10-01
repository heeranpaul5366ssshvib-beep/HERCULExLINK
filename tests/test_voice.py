"""Voice subsystem tests (v1.1): config, availability honesty, routing,
async speech, UI/HUD state, privacy defaults. Fakes live here in the
test process only — production code never fabricates audio or transcripts.
No physical microphone is required.
"""
import threading
import time

import pytest

from voice.config import VoiceConfig, load_voice_config
from voice.controller import VoiceController
from voice.input import AudioCapture, MicInput, VoiceUnavailable, list_input_devices
from voice.output import AsyncSpeaker
from voice.speech_to_text import SpeechRecognitionSTT, get_stt_provider
from voice.text_to_speech import get_tts_provider


class FakeApp:
    """Stand-in for HerculeAppController: records the typed-input path."""

    def __init__(self):
        self.submitted = []
        from brain.consciousness import Consciousness
        self.brain = type("Brain", (), {"consciousness": Consciousness()})()

    def submit(self, text):
        self.submitted.append(text)
        return {"kind": "QUESTION", "status": "answered", "response": f"echo:{text}"}

    def format_response(self, result):
        return result.get("response", "")


class FakeSTT:
    name = "fake"

    def __init__(self, transcript="calculate 25 * 4"):
        self.transcript = transcript
        self.calls = 0

    def available(self):
        return {"available": True, "engine": "fake"}

    def transcribe(self, audio):
        self.calls += 1
        return self.transcript


# --------------------------------------------------
# Configuration
# --------------------------------------------------
def test_voice_disabled_by_default_and_no_keys():
    config = load_voice_config(env={})
    assert config.enabled is False
    assert config.persist_audio is False
    blob = str(config.as_dict())
    assert "key" not in blob.lower() and "token" not in blob.lower()


def test_voice_env_overrides_and_clamping():
    config = load_voice_config(env={
        "HERCULE_VOICE_ENABLED": "1",
        "HERCULE_VOICE_RATE": "9999",
        "HERCULE_VOICE_LISTEN_TIMEOUT_S": "0",
    })
    assert config.enabled is True
    assert config.rate == 400  # clamped
    assert config.listen_timeout_s == 1.0  # floored
    assert isinstance(VoiceConfig().as_dict(), dict)


# --------------------------------------------------
# Microphone honesty (no hardware required)
# --------------------------------------------------
def test_input_probe_shape_without_recording():
    inputs = list_input_devices()
    assert isinstance(inputs, list)
    for device in inputs:
        assert {"index", "name", "max_input_channels"} <= set(device)


def test_unknown_microphone_reports_honestly():
    mic = MicInput(device="no-such-mic-xyz")
    probe = mic.availability()
    assert probe["available"] is False
    assert "reason" in probe


def test_capture_without_device_raises_not_fakes():
    mic = MicInput(device="no-such-mic-xyz")
    with pytest.raises(VoiceUnavailable):
        mic.capture_once(timeout_s=1.0)
    assert mic.capturing is False


def test_audio_capture_metrics():
    capture = AudioCapture(samples=b"\x00\x00" * 16000, sample_rate=16000)
    assert capture.seconds == pytest.approx(1.0)
    assert capture.as_dict()["bytes"] == 32000


# --------------------------------------------------
# STT honesty
# --------------------------------------------------
def test_unknown_stt_provider_rejected():
    with pytest.raises(ValueError, match="unknown STT provider"):
        get_stt_provider("cloud-magic")


def test_stt_empty_audio_never_transcribed():
    stt = SpeechRecognitionSTT()
    probe = stt.available()
    assert set(probe) >= {"available"}
    with pytest.raises((ValueError, VoiceUnavailable)):
        stt.transcribe(AudioCapture(samples=b""))


def test_stt_reports_engine_or_reason():
    probe = SpeechRecognitionSTT().available()
    if probe["available"]:
        assert probe.get("engine")
    else:
        assert "reason" in probe and "whisper" in probe["reason"].lower()


# --------------------------------------------------
# Pipeline routing (same path as typed input)
# --------------------------------------------------
def test_transcript_routes_through_app_submit():
    app = FakeApp()
    voice = VoiceController(app, VoiceConfig(enabled=True))
    text = voice.submit_transcript("calculate 25 * 4")
    assert app.submitted == ["calculate 25 * 4"]
    assert text == "echo:calculate 25 * 4"
    assert voice.snapshot()["last_transcript"] == "calculate 25 * 4"


def test_empty_transcript_submits_nothing():
    app = FakeApp()
    voice = VoiceController(app, VoiceConfig(enabled=True))
    assert voice.submit_transcript("   ") == ""
    assert app.submitted == []


def test_listen_rejected_while_disabled():
    voice = VoiceController(FakeApp(), VoiceConfig(enabled=False))
    assert voice.listen_once()["status"] == "rejected"
    assert voice.speak("hi")["status"] == "rejected"


def test_full_turn_with_fakes():
    app = FakeApp()
    voice = VoiceController(app, VoiceConfig(enabled=True))
    voice._stt = FakeSTT("calculate 25 * 4")
    voice.mic = MicInput(device="no-such-mic")
    # Mic unavailable -> honest voice error, never fabricated transcript.
    voice.listen_once()
    deadline = time.time() + 5
    while voice.snapshot()["listening"] and time.time() < deadline:
        time.sleep(0.05)
    assert app.submitted == []
    assert "unavailable" in voice.snapshot()["last_response"].lower()


# --------------------------------------------------
# TTS + async speaker
# --------------------------------------------------
def test_unknown_tts_provider_rejected():
    with pytest.raises(ValueError, match="unknown TTS provider"):
        get_tts_provider("cloud-voice")


def test_speaker_is_async_and_ordered():
    spoken = []
    gate = threading.Event()
    speaker = AsyncSpeaker(lambda text: (spoken.append(text), gate.wait(2)))
    first = speaker.speak_async("one")
    speaker.speak_async("two")
    assert isinstance(first, str) and first
    time.sleep(0.2)
    assert spoken == [] or spoken == ["one"]  # worker owns timing, never caller
    gate.set()
    deadline = time.time() + 5
    while len(spoken) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert spoken == ["one", "two"]


def test_speaker_stop_drains_and_mute_suppresses():
    spoken = []
    speaker = AsyncSpeaker(spoken.append)
    assert speaker.set_muted(True) is True
    speaker.speak_async("silent")
    time.sleep(0.3)
    assert spoken == []
    assert speaker.set_muted(False) is False
    assert speaker.stop()["stopped"] is True


def test_muted_speak_keeps_text():
    voice = VoiceController(FakeApp(), VoiceConfig(enabled=True))
    voice.set_muted(True)
    assert voice.speak("hello")["status"] == "muted"


def test_tts_stop_interrupts_blocked_speech():
    # Regression: speak() must not hold the provider lock across the
    # blocking runAndWait(), or stop()/cancel() deadlocks against
    # in-flight speech (observed with SAPI5 and no audio device).
    from voice.text_to_speech import Pyttsx3TTS
    started = threading.Event()
    release = threading.Event()

    class BlockingEngine:
        def say(self, text):
            started.set()

        def runAndWait(self):
            release.wait(30)  # blocks like a device-less SAPI5 loop

        def stop(self):
            release.set()

    tts = Pyttsx3TTS()
    tts._engine = BlockingEngine()
    tts._probe = {"available": True, "engine": "test"}
    worker = threading.Thread(target=lambda: tts.speak("hello"), daemon=True)
    worker.start()
    assert started.wait(10)
    deadline = time.time() + 15
    assert tts.stop()["stopped"] is True  # must return, never deadlock
    assert time.time() < deadline
    worker.join(timeout=15)
    assert not worker.is_alive()


# --------------------------------------------------
# Controller state / HUD snapshot / privacy
# --------------------------------------------------
def test_snapshot_keys_and_privacy_defaults():
    voice = VoiceController(FakeApp(), VoiceConfig())
    snap = voice.snapshot()
    assert snap["enabled"] is False
    assert snap["mic_on"] is False
    assert snap["listening"] is False
    assert snap["speaking"] is False
    assert snap["muted"] is False
    assert snap["state"] == "IDLE"
    assert set(snap) >= {"enabled", "state", "listening", "speaking",
                         "muted", "mic_on", "last_transcript",
                         "last_response", "inputs"}


def test_enable_disable_cancel_cycle():
    voice = VoiceController(FakeApp(), VoiceConfig())
    assert voice.enable()["enabled"] is True
    assert voice.cancel()["status"] == "stopped"
    assert voice.disable()["enabled"] is False
    assert voice.snapshot()["state"] == "IDLE"


def test_no_audio_persisted_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    voice = VoiceController(FakeApp(), VoiceConfig())
    assert voice.config.persist_audio is False
    voice.stop()
    leftovers = [p for p in tmp_path.rglob("*")
                 if p.suffix.lower() in (".wav", ".mp3", ".raw", ".pcm")]
    assert leftovers == []


def test_consciousness_speaking_state_valid():
    from brain.consciousness import Consciousness, VALID_STATES
    assert "SPEAKING" in VALID_STATES
    consciousness = Consciousness()
    consciousness.set_state("ACTIVE", "test")
    assert consciousness.transition("SPEAKING", "voice test") == "SPEAKING"
    with pytest.raises(ValueError, match="illegal consciousness transition"):
        Consciousness().transition("SPEAKING", "from IDLE is illegal")


def test_desktop_voice_panel_when_display_available():
    pytest.importorskip("tkinter")
    import tkinter as tk
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
    except Exception as exc:
        pytest.skip(f"no display available: {exc}")
    from interface.app_controller import HerculeAppController
    from interface.desktop_app import HerculeDesktopApp
    from runtime.initializer import RuntimeInitializer
    import os
    os.environ.setdefault("HERCULE_DEFAULT_MODEL", "mock")
    os.environ.setdefault("HERCULE_ALLOW_MOCK", "1")
    os.environ.setdefault("HERCULE_TASK_STORE", ":memory:")
    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    voice = VoiceController(controller, VoiceConfig())
    root = tk.Tk()
    root.withdraw()
    try:
        app = HerculeDesktopApp(controller, root=root, voice=voice)
        app._refresh()
        assert "OFF" in app.voice_var.get()
        assert app.voice_text_var.get().startswith("say:")
    finally:
        root.destroy()
