from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Voice Controller (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Voice conversation control over the EXISTING pipeline. Transcripts
enter through ``app_controller.submit()`` — the exact path typed
input takes (RequestRouter -> Brain -> planning/execution/
verification). Voice adds no request processing, no execution, and
no policy of its own.

States (all pre-existing Consciousness states): IDLE, LISTENING,
UNDERSTANDING, THINKING, EXECUTING, SPEAKING. Voice is opt-in and
off by default; the microphone is only touched during an explicit
listen call; nothing is recorded continuously and nothing is
persisted unless the operator enables persist_audio.
"""

import threading
from typing import Any, Dict, Optional

from voice.config import VoiceConfig, load_voice_config
from voice.input import AudioCapture, MicInput, VoiceUnavailable, list_input_devices
from voice.output import AsyncSpeaker
from voice.speech_to_text import get_stt_provider
from voice.text_to_speech import get_tts_provider


class VoiceController:
    """Bridges microphone/speaker hardware and the live HERCULE runtime."""

    def __init__(self, app_controller, config: Optional[VoiceConfig] = None):
        self.app = app_controller
        self.config = config or load_voice_config()
        self.mic = MicInput(device=self.config.microphone)
        self._stt = None
        self._tts = None
        self._speaker: Optional[AsyncSpeaker] = None
        # RLock: listen_once()/stop() legitimately set state (which locks)
        # while already holding the controller lock. A plain Lock would
        # self-deadlock the calling thread on voice start/stop.
        self._lock = threading.RLock()
        self._listen_thread: Optional[threading.Thread] = None
        self._listening = False
        self._state = "IDLE"
        self._muted = False
        self._last_transcript = ""
        self._last_response = ""
        self._last_result: Optional[Dict[str, Any]] = None

    # --------------------------------------------------
    # Providers (lazy: nothing loads until first use)
    # --------------------------------------------------
    def _stt_provider(self):
        if self._stt is None:
            self._stt = get_stt_provider(self.config.stt_provider)
        return self._stt

    def _tts_provider(self):
        if self._tts is None:
            self._tts = get_tts_provider(
                self.config.tts_provider, rate=self.config.rate,
                voice=self.config.voice)
        return self._tts

    def _speaker_or_raise(self) -> AsyncSpeaker:
        provider = self._tts_provider()
        probe = provider.available()
        if not probe.get("available"):
            raise VoiceUnavailable(str(probe.get("reason", "TTS unavailable")))
        if self._speaker is None:
            tts = provider

            def _say(text: str) -> None:
                tts.speak(text)

            self._speaker = AsyncSpeaker(_say, interrupt=tts.stop)
            self._speaker.set_muted(self._muted)
        return self._speaker

    # --------------------------------------------------
    # Availability (honest probes: no recording, no model calls)
    # --------------------------------------------------
    def availability(self) -> Dict[str, Any]:
        mic = self.mic.availability()
        try:
            stt = self._stt_provider().available()
        except Exception as exc:
            stt = {"available": False, "reason": str(exc)[:160]}
        try:
            tts = self._tts_provider().available()
        except Exception as exc:
            tts = {"available": False, "reason": str(exc)[:160]}
        return {"enabled": bool(self.config.enabled), "mic": mic, "stt": stt,
                "tts": tts,
                "voice_ready": bool(self.config.enabled and mic.get("available")
                                    and stt.get("available"))}

    # --------------------------------------------------
    # Enable / mute (opt-in control)
    # --------------------------------------------------
    def enable(self) -> Dict[str, Any]:
        self.config.enabled = True
        return {"enabled": True, **self.availability()}

    def disable(self) -> Dict[str, Any]:
        self.stop()
        self.config.enabled = False
        return {"enabled": False}

    def set_muted(self, muted: bool) -> Dict[str, Any]:
        self._muted = bool(muted)
        if self._speaker is not None:
            self._speaker.set_muted(self._muted)
        return {"muted": self._muted}

    # --------------------------------------------------
    # Conversation control: LISTEN / STOP / SPEAK / CANCEL
    # --------------------------------------------------
    def listen_once(self) -> Dict[str, Any]:
        """Start one background listen->transcribe->respond->speak turn."""
        with self._lock:
            if not self.config.enabled:
                return {"status": "rejected", "reason": "voice is disabled (opt-in)"}
            if self._listening:
                return {"status": "rejected", "reason": "already listening"}
            try:
                thread = threading.Thread(target=self._listen_turn, daemon=True)
                self._listening = True
                self._set_state("LISTENING")
                thread.start()
                self._listen_thread = thread
            except Exception as exc:
                self._listening = False
                return {"status": "failed", "error": str(exc)[:200]}
        return {"status": "listening"}

    def stop(self) -> Dict[str, Any]:
        """Stop listening and silence speech (idempotent)."""
        self.mic.stop()
        if self._speaker is not None:
            try:
                self._speaker.stop()
            except Exception:
                pass
        with self._lock:
            self._listening = False
            self._set_state("IDLE")
        return {"status": "stopped"}

    def cancel(self) -> Dict[str, Any]:
        """Alias for stop (voice cancel control)."""
        return self.stop()

    def speak(self, text: str) -> Dict[str, Any]:
        """Speak a response asynchronously (never blocks the caller)."""
        if not self.config.enabled:
            return {"status": "rejected", "reason": "voice is disabled (opt-in)"}
        if self._muted:
            return {"status": "muted", "text": str(text or "")[:200]}
        try:
            speaker = self._speaker_or_raise()
        except VoiceUnavailable as exc:
            return {"status": "unavailable", "reason": str(exc)[:200],
                    "text": str(text or "")[:200]}
        utterance_id = speaker.speak_async(text)
        self._set_state("SPEAKING")
        return {"status": "speaking", "utterance_id": utterance_id}

    # --------------------------------------------------
    # The turn: mic -> STT -> SAME pipeline -> TTS
    # --------------------------------------------------
    def _listen_turn(self) -> None:
        transcript = ""
        try:
            self._consciousness("LISTENING", "voice capture")
            audio = self.mic.capture_once(
                timeout_s=self.config.listen_timeout_s,
                silence_timeout_s=self.config.silence_timeout_s)
            self._consciousness("UNDERSTANDING", "voice transcript")
            transcript = self._stt_provider().transcribe(audio).strip()
            with self._lock:
                self._last_transcript = transcript
            if not transcript:
                self._set_state("IDLE")
                return
            response = self.submit_transcript(transcript)
            with self._lock:
                self._last_response = response
            self.speak(response)
        except (VoiceUnavailable, TimeoutError, ValueError) as exc:
            with self._lock:
                self._last_response = f"[Voice unavailable] {exc}"
            self._set_state("IDLE")
        except Exception as exc:
            with self._lock:
                self._last_response = f"[Voice error] {exc}"
            self._set_state("IDLE")
        finally:
            with self._lock:
                self._listening = False
            if self._state == "LISTENING":
                self._set_state("IDLE")

    def submit_transcript(self, transcript: str) -> str:
        """Route one transcript through the EXISTING typed-input pipeline.

        Uses app_controller.submit() + format_response() — identical to
        the desktop console path. No voice-specific execution exists.
        """
        cleaned = str(transcript or "").strip()
        if not cleaned:
            return ""
        with self._lock:
            self._last_transcript = cleaned
        self._consciousness("THINKING", f"voice:{cleaned[:60]}")
        try:
            result = self.app.submit(cleaned)
            text = self.app.format_response(result) or "(empty response)"
        except Exception as exc:
            text = f"[HERCULE Error] {exc}"
        with self._lock:
            self._last_response = text
            self._last_result = result if isinstance(result, dict) else None
        return text

    # --------------------------------------------------
    # State + HUD snapshot (real values only)
    # --------------------------------------------------
    def _set_state(self, state: str) -> None:
        with self._lock:
            self._state = state

    def _consciousness(self, state: str, reason: str) -> None:
        try:
            brain = getattr(self.app, "brain", None)
            consciousness = getattr(brain, "consciousness", None)
            if consciousness is not None and hasattr(consciousness, "set_state"):
                consciousness.set_state(state, reason)
        except Exception:
            pass

    def snapshot(self) -> Dict[str, Any]:
        """Voice/HUD state: real values, never fabricated mic/model states."""
        with self._lock:
            speaker = self._speaker
            speaking = bool(speaker.speaking) if speaker is not None else False
            state = self._state
            if speaking:
                state = "SPEAKING"
            return {
                "enabled": bool(self.config.enabled),
                "state": state,
                "listening": bool(self._listening),
                "speaking": speaking,
                "muted": bool(self._muted),
                "mic_on": bool(self._listening),
                "last_transcript": self._last_transcript[:200],
                "last_response": self._last_response[:200],
                "inputs": [d["name"] for d in list_input_devices()],
            }
