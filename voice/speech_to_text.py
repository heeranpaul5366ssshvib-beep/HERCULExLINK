from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Speech-To-Text Providers (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Provider-neutral speech recognition. Default is fully local
(SpeechRecognition + local whisper/sphinx engines when present):
no cloud, no API keys. When no local engine is available the
provider reports UNAVAILABLE with a reason — transcription is
never fabricated.
"""

from typing import Any, Dict, Optional

from voice.input import AudioCapture, VoiceUnavailable


class STTProvider:
    """Speech-to-text engine interface (replaceable)."""

    name = "base"

    def available(self) -> Dict[str, Any]:
        raise NotImplementedError

    def transcribe(self, audio: AudioCapture) -> str:
        raise NotImplementedError


class SpeechRecognitionSTT(STTProvider):
    """Local STT via SpeechRecognition + a local engine.

    Engine choice (checked lazily, in order): openai-whisper (local
    model, needs torch) then pocketsphinx (fully offline). Cloud
    recognizers are deliberately never used: transcripts must not
    leave the machine by default.
    """

    name = "speech_recognition"

    def available(self) -> Dict[str, Any]:
        try:
            import speech_recognition  # noqa: F401
        except Exception:
            return {"available": False,
                    "reason": "SpeechRecognition not installed (pip install SpeechRecognition)"}
        engine = self._local_engine()
        if engine is None:
            return {"available": False,
                    "reason": ("no local speech engine: install openai-whisper "
                               "(needs torch) or pocketsphinx for offline STT")}
        return {"available": True, "engine": engine}

    @staticmethod
    def _local_engine() -> Optional[str]:
        try:
            import whisper  # noqa: F401
            return "whisper-local"
        except Exception:
            pass
        try:
            import pocketsphinx  # noqa: F401
            return "sphinx-offline"
        except Exception:
            pass
        return None

    def transcribe(self, audio: AudioCapture) -> str:
        probe = self.available()
        if not probe.get("available"):
            raise VoiceUnavailable(str(probe.get("reason", "STT unavailable")))
        if not audio.samples:
            raise ValueError("empty audio capture: nothing to transcribe")
        try:
            import speech_recognition as _sr
        except Exception as exc:
            raise VoiceUnavailable(f"SpeechRecognition unavailable: {exc}")
        recognizer = _sr.Recognizer()
        data = _sr.AudioData(audio.samples, audio.sample_rate, audio.sample_width)
        engine = probe.get("engine")
        try:
            if engine == "whisper-local":
                return str(recognizer.recognize_whisper(data))
            return str(recognizer.recognize_sphinx(data))
        except _sr.UnknownValueError:
            raise ValueError("speech unintelligible: no transcript produced")
        except Exception as exc:
            raise VoiceUnavailable(f"local transcription failed: {exc}")


def get_stt_provider(name: str = "speech_recognition") -> STTProvider:
    """Resolve a provider by name (unknown names fail loudly)."""
    providers = {"speech_recognition": SpeechRecognitionSTT}
    key = str(name or "speech_recognition").strip().lower()
    if key not in providers:
        raise ValueError(f"unknown STT provider: {name!r} "
                         f"(available: {sorted(providers)})")
    return providers[key]()
