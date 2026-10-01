from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Voice Input - Microphone Capture (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Provider-neutral microphone input. Audio is captured into memory only
while an explicit capture is active — never continuously, never written
to disk (unless the operator enables persist_audio, handled by the
controller, not here). Missing libraries or missing input devices
report UNAVAILABLE honestly instead of faking audio.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class VoiceUnavailable(RuntimeError):
    """Raised when voice input/output genuinely cannot run here."""


@dataclass
class AudioCapture:
    """In-memory PCM mono capture (never persisted by this module)."""
    samples: bytes = b""
    sample_rate: int = 16000
    sample_width: int = 2
    channels: int = 1

    @property
    def seconds(self) -> float:
        frames = len(self.samples) // max(1, self.sample_width * self.channels)
        return frames / float(self.sample_rate or 16000)

    def as_dict(self) -> Dict[str, Any]:
        return {"sample_rate": self.sample_rate, "sample_width": self.sample_width,
                "channels": self.channels, "seconds": round(self.seconds, 2),
                "bytes": len(self.samples)}


def list_input_devices() -> List[Dict[str, Any]]:
    """Audio input devices present on this machine (honest, may be empty)."""
    try:
        import sounddevice as _sd
    except Exception:
        return []
    try:
        devices = _sd.query_devices()
    except Exception:
        return []
    inputs = []
    for index, device in enumerate(devices):
        try:
            name = str(device.get("name", f"device-{index}"))
            max_inputs = int(device.get("max_input_channels", 0) or 0)
        except Exception:
            continue
        if max_inputs > 0:
            inputs.append({"index": index, "name": name,
                           "max_input_channels": max_inputs})
    return inputs


def default_input_index() -> Optional[int]:
    """Default OS input device index, or None when no input exists."""
    try:
        import sounddevice as _sd
        default = _sd.default.device
        index = default[0] if isinstance(default, (list, tuple)) else default
        if index is None or int(index) < 0:
            return None
        return int(index)
    except Exception:
        return None


@dataclass
class MicInput:
    """Explicit, bounded microphone capture (opt-in per capture call)."""

    device: str = ""
    sample_rate: int = 16000
    _capturing: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def availability(self) -> Dict[str, Any]:
        """Honest capability probe (no recording, no model calls)."""
        try:
            import sounddevice  # noqa: F401
        except Exception:
            return {"available": False,
                    "reason": "sounddevice not installed (pip install sounddevice)"}
        inputs = list_input_devices()
        if not inputs:
            return {"available": False,
                    "reason": "no microphone input device on this machine"}
        if self.device:
            wanted = self.device.strip().lower()
            match = [d for d in inputs
                     if wanted in (str(d["name"]).lower(), str(d["index"]))]
            if not match:
                return {"available": False,
                        "reason": f"microphone not found: {self.device!r}",
                        "inputs": [d["name"] for d in inputs]}
        return {"available": True, "inputs": inputs}

    @property
    def capturing(self) -> bool:
        with self._lock:
            return self._capturing

    def capture_once(self, timeout_s: float = 8.0,
                     silence_timeout_s: float = 2.0) -> AudioCapture:
        """Record one bounded utterance into memory and return it.

        Raises VoiceUnavailable when capture is impossible here.
        Raises TimeoutError when nothing was captured in time.
        """
        probe = self.availability()
        if not probe.get("available"):
            raise VoiceUnavailable(str(probe.get("reason", "microphone unavailable")))
        try:
            import sounddevice as _sd
            import numpy as _np
        except Exception as exc:
            raise VoiceUnavailable(f"capture libraries unavailable: {exc}")
        device_index: Optional[int] = None
        if self.device:
            for candidate in list_input_devices():
                if self.device.strip().lower() in (str(candidate["name"]).lower(),
                                                   str(candidate["index"])):
                    device_index = int(candidate["index"])
                    break
            if device_index is None:
                raise VoiceUnavailable(f"microphone not found: {self.device!r}")
        frames: List[bytes] = []
        deadline = __import__("time").perf_counter() + max(1.0, float(timeout_s or 8.0))
        with self._lock:
            self._capturing = True
        try:
            # Bounded capture: stops at timeout_s or on stop(). True
            # voice-activity detection is engine-dependent and lives in
            # the STT layer; the bound alone guarantees no open-ended
            # recording (see silence_timeout_s in VoiceConfig for
            # engines that support trailing-silence stop).
            with _sd.InputStream(samplerate=self.sample_rate, channels=1,
                                 dtype="int16", device=device_index,
                                 blocksize=self.sample_rate // 4) as stream:
                while __import__("time").perf_counter() < deadline:
                    with self._lock:
                        if not self._capturing:
                            break
                    chunk, _overflow = stream.read(self.sample_rate // 4)
                    frames.append(bytes(chunk))
        finally:
            with self._lock:
                self._capturing = False
        raw = b"".join(frames)
        if not raw:
            raise TimeoutError("no audio captured before timeout")
        return AudioCapture(samples=raw, sample_rate=self.sample_rate)

    def stop(self) -> None:
        """Request the active capture loop to end (idempotent)."""
        with self._lock:
            self._capturing = False
