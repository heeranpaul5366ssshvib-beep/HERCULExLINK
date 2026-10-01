from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Text-To-Speech Providers (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Provider-neutral speech synthesis. Default is fully local
(pyttsx3, SAPI5 on Windows): no cloud, no API keys. When the
engine is unavailable the provider reports UNAVAILABLE with a
reason — successful speech is never fabricated, and callers
fall back to text display.
"""

import threading
from typing import Any, Dict, Optional

from voice.input import VoiceUnavailable
from voice.output import AsyncSpeaker


class TTSProvider:
    """Text-to-speech engine interface (replaceable)."""

    name = "base"

    def available(self) -> Dict[str, Any]:
        raise NotImplementedError

    def speak(self, text: str) -> Dict[str, Any]:
        """Speak synchronously; returns a structured receipt."""
        raise NotImplementedError

    def stop(self) -> Dict[str, Any]:
        return {"stopped": True}


class Pyttsx3TTS(TTSProvider):
    """Local TTS via pyttsx3 (offline SAPI5 voice on Windows)."""

    name = "pyttsx3"

    def __init__(self, rate: int = 175, voice: str = ""):
        self.rate = rate
        self.voice = voice
        self._engine: Any = None
        self._lock = threading.Lock()
        self._probe: Optional[Dict[str, Any]] = None

    def available(self) -> Dict[str, Any]:
        if self._probe is not None:
            return dict(self._probe)
        try:
            import pyttsx3  # noqa: F401
        except Exception:
            self._probe = {"available": False,
                           "reason": "pyttsx3 not installed (pip install pyttsx3)"}
            return dict(self._probe)
        try:
            engine = self._build_engine()
            try:
                engine.stop()
            except Exception:
                pass
            self._engine = engine
            self._probe = {"available": True, "engine": "sapi5-local"}
        except Exception as exc:
            self._probe = {"available": False,
                           "reason": f"TTS engine init failed: {exc}"}
        return dict(self._probe)

    def _build_engine(self) -> Any:
        import pyttsx3

        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", int(self.rate))
        except Exception:
            pass
        if self.voice:
            try:
                for candidate in engine.getProperty("voices") or []:
                    blob = f"{getattr(candidate, 'id', '')} {getattr(candidate, 'name', '')}".lower()
                    if self.voice.strip().lower() in blob:
                        engine.setProperty("voice", candidate.id)
                        break
            except Exception:
                pass
        return engine

    def _engine_or_raise(self) -> Any:
        probe = self.available()
        if not probe.get("available"):
            raise VoiceUnavailable(str(probe.get("reason", "TTS unavailable")))
        return self._take_engine()

    def _take_engine(self) -> Any:
        """Return the shared engine without holding the lock across speech.

        The lock guards engine swap-in/out only. Blocking runAndWait()
        must never run under this lock, otherwise stop() (which needs
        the lock to swap the engine out) deadlocks against in-flight
        speech and CANCEL can never silence it.
        """
        with self._lock:
            if self._engine is None:
                self._engine = self._build_engine()
            return self._engine

    def speak(self, text: str) -> Dict[str, Any]:
        """Speak one response synchronously (AsyncSpeaker wraps this)."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return {"status": "skipped", "reason": "empty text"}
        engine = self._engine_or_raise()
        try:
            engine.say(cleaned)
            engine.runAndWait()
        except Exception as exc:
            raise VoiceUnavailable(f"speech synthesis failed: {exc}")
        return {"status": "spoken", "chars": len(cleaned)}

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            engine, self._engine = self._engine, None
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
        # Fresh engine next time (pyttsx3 loops do not survive stop()).
        self._probe = None
        return {"stopped": True}

    def synthesize_to_file(self, text: str, path: str) -> Dict[str, Any]:
        """Render speech to a WAV file (diagnostics opt-in only)."""
        cleaned = str(text or "").strip()
        if not cleaned:
            return {"status": "skipped", "reason": "empty text"}
        engine = self._engine_or_raise()
        try:
            engine.save_to_file(cleaned, str(path))
            engine.runAndWait()
        except Exception as exc:
            raise VoiceUnavailable(f"file synthesis failed: {exc}")
        return {"status": "saved", "path": str(path), "chars": len(cleaned)}


def get_tts_provider(name: str = "pyttsx3", **kwargs: Any) -> TTSProvider:
    """Resolve a provider by name (unknown names fail loudly)."""
    providers = {"pyttsx3": Pyttsx3TTS}
    key = str(name or "pyttsx3").strip().lower()
    if key not in providers:
        raise ValueError(f"unknown TTS provider: {name!r} "
                         f"(available: {sorted(providers)})")
    return providers[key](**kwargs)
