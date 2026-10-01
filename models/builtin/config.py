from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Built-in Provider Configuration (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Explicit dict > HERCULE_MODEL_*/HERCULE_BUILTIN_*/HERCULE_OFFLINE env
vars > safe defaults. The built-in provider is selected only when
configured (HERCULE_MODEL_PROVIDER=builtin) or when offline mode
forces it; default runs keep the historical Ollama-first behavior
byte-identically. No API keys anywhere.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_ENV_MAP = (
    ("HERCULE_MODEL_PROVIDER", "provider"),
    ("HERCULE_MODEL_PATH", "model_path"),
    ("HERCULE_MODEL_ID", "model_id"),
    ("HERCULE_OFFLINE", "offline"),
    ("HERCULE_BUILTIN_CTX", "ctx_size"),
    ("HERCULE_BUILTIN_THREADS", "threads"),
    ("HERCULE_BUILTIN_TEMP", "temperature"),
    ("HERCULE_BUILTIN_TOP_P", "top_p"),
    ("HERCULE_BUILTIN_MAX_TOKENS", "max_tokens"),
    ("HERCULE_BUILTIN_GPU_LAYERS", "gpu_layers"),
    ("HERCULE_BUILTIN_PORT", "port"),
    ("HERCULE_BUILTIN_TIMEOUT_S", "timeout_s"),
)

_DEFAULTS: Dict[str, Any] = {
    "provider": "auto",
    "model_path": "",
    "model_id": "hercule-local",
    "offline": False,
    "ctx_size": 4096,
    "threads": 0,  # 0 = auto (physical cores minus one, min 1)
    "temperature": 0.7,
    "top_p": 0.9,
    "max_tokens": 512,
    "gpu_layers": 0,  # 0 = CPU; >0 only when a GPU is detected
    "port": 0,  # 0 = ephemeral loopback port
    "timeout_s": 120.0,
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class BuiltinConfig:
    provider: str = "auto"  # auto | builtin | ollama
    model_path: str = ""
    model_id: str = "hercule-local"
    offline: bool = False
    ctx_size: int = 4096
    threads: int = 0
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 512
    gpu_layers: int = 0
    port: int = 0
    timeout_s: float = 120.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_path": self.model_path,
            "model_id": self.model_id,
            "offline": self.offline,
            "ctx_size": self.ctx_size,
            "threads": self.threads,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "gpu_layers": self.gpu_layers,
            "port": self.port,
            "timeout_s": self.timeout_s,
        }


def load_builtin_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> BuiltinConfig:
    source = dict(env) if env is not None else dict(os.environ)
    merged: Dict[str, Any] = dict(_DEFAULTS)
    for env_key, field_name in _ENV_MAP:
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
    provider = str(merged.get("provider", "auto")).strip().lower()
    if provider not in ("auto", "builtin", "ollama"):
        provider = "auto"

    def _int(key: str, default: int, lo: int, hi: int) -> int:
        try:
            value = int(merged.get(key, default))
        except (TypeError, ValueError):
            value = default
        return min(hi, max(lo, value))

    def _float(key: str, default: float, lo: float, hi: float) -> float:
        try:
            value = float(merged.get(key, default))
        except (TypeError, ValueError):
            value = default
        return min(hi, max(lo, value))

    return BuiltinConfig(
        provider=provider,
        model_path=str(merged.get("model_path", "") or ""),
        model_id=str(merged.get("model_id", "") or "hercule-local"),
        offline=_as_bool(merged.get("offline", False)),
        ctx_size=_int("ctx_size", 4096, 512, 131072),
        threads=_int("threads", 0, 0, 256),
        temperature=_float("temperature", 0.7, 0.0, 2.0),
        top_p=_float("top_p", 0.9, 0.0, 1.0),
        max_tokens=_int("max_tokens", 512, 1, 16384),
        gpu_layers=_int("gpu_layers", 0, 0, 1000),
        port=_int("port", 0, 0, 65535),
        timeout_s=_float("timeout_s", 120.0, 5.0, 600.0),
    )


def default_threads() -> int:
    """Sensible CPU default: physical cores minus one, minimum 1."""
    try:
        count = int(os.cpu_count() or 2)
    except Exception:
        count = 2
    return max(1, count - 1)


def detect_gpu() -> Dict[str, Any]:
    """GPU presence probe (honest: CPU unless proven otherwise)."""
    try:
        import torch

        if bool(torch.cuda.is_available()):
            return {"present": True, "backend": "cuda",
                    "name": str(torch.cuda.get_device_name(0))}
    except Exception:
        pass
    return {"present": False, "backend": "cpu", "name": ""}
