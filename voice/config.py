from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Voice Configuration (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Voice settings: explicit dict > HERCULE_VOICE_* env vars > safe
defaults. Voice is OFF by default (opt-in), local-only, and needs no
API keys. No raw audio is ever persisted unless persist_audio is
explicitly enabled by the operator.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


_ENV_MAP = (
    ("HERCULE_VOICE_ENABLED", "enabled"),
    ("HERCULE_VOICE_MIC", "microphone"),
    ("HERCULE_VOICE_STT", "stt_provider"),
    ("HERCULE_VOICE_TTS", "tts_provider"),
    ("HERCULE_VOICE_NAME", "voice"),
    ("HERCULE_VOICE_RATE", "rate"),
    ("HERCULE_VOICE_LISTEN_TIMEOUT_S", "listen_timeout_s"),
    ("HERCULE_VOICE_SILENCE_TIMEOUT_S", "silence_timeout_s"),
    ("HERCULE_VOICE_PERSIST_AUDIO", "persist_audio"),
)

_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "microphone": "",
    "stt_provider": "speech_recognition",
    "tts_provider": "pyttsx3",
    "voice": "",
    "rate": 175,
    "listen_timeout_s": 8.0,
    "silence_timeout_s": 2.0,
    "persist_audio": False,
}


@dataclass
class VoiceConfig:
    enabled: bool = False
    microphone: str = ""
    stt_provider: str = "speech_recognition"
    tts_provider: str = "pyttsx3"
    voice: str = ""
    rate: int = 175
    listen_timeout_s: float = 8.0
    silence_timeout_s: float = 2.0
    persist_audio: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "microphone": self.microphone,
            "stt_provider": self.stt_provider,
            "tts_provider": self.tts_provider,
            "voice": self.voice,
            "rate": self.rate,
            "listen_timeout_s": self.listen_timeout_s,
            "silence_timeout_s": self.silence_timeout_s,
            "persist_audio": self.persist_audio,
        }


def load_voice_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> VoiceConfig:
    """Build config: explicit dict > HERCULE_VOICE_* env > safe defaults."""
    source = dict(env) if env is not None else dict(os.environ)
    merged: Dict[str, Any] = dict(_DEFAULTS)
    for env_key, field_name in _ENV_MAP:
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
    try:
        rate = int(merged.get("rate", 175))
    except (TypeError, ValueError):
        rate = 175
    rate = min(400, max(50, rate))
    try:
        listen_timeout = float(merged.get("listen_timeout_s", 8.0))
        silence_timeout = float(merged.get("silence_timeout_s", 2.0))
    except (TypeError, ValueError):
        listen_timeout, silence_timeout = 8.0, 2.0
    listen_timeout = min(60.0, max(1.0, listen_timeout))
    silence_timeout = min(10.0, max(0.5, silence_timeout))
    return VoiceConfig(
        enabled=_as_bool(merged.get("enabled", False)),
        microphone=str(merged.get("microphone", "") or ""),
        stt_provider=str(merged.get("stt_provider", "") or "speech_recognition"),
        tts_provider=str(merged.get("tts_provider", "") or "pyttsx3"),
        voice=str(merged.get("voice", "") or ""),
        rate=rate,
        listen_timeout_s=listen_timeout,
        silence_timeout_s=silence_timeout,
        persist_audio=_as_bool(merged.get("persist_audio", False)),
    )
