from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Vision Configuration (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Explicit dict > HERCULE_VISION_* env vars > safe defaults. Vision is
read-only and explicitly requested (never continuous). No API keys, no
cloud: only local vision-capable models discovered on the Ollama server.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


_ENV_MAP = (
    ("HERCULE_VISION_MODEL", "model"),
    ("HERCULE_VISION_TIMEOUT_S", "timeout_s"),
    ("HERCULE_VISION_MAX_DIM", "max_dim_px"),
    ("HERCULE_VISION_OCR", "ocr_enabled"),
    ("HERCULE_VISION_MAX_BYTES", "max_bytes"),
)

_DEFAULTS: Dict[str, Any] = {
    "model": "",
    "timeout_s": 60.0,
    "max_dim_px": 1280,
    "ocr_enabled": True,
    "max_bytes": 10 * 1024 * 1024,
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class VisionConfig:
    model: str = ""
    timeout_s: float = 60.0
    max_dim_px: int = 1280
    ocr_enabled: bool = True
    max_bytes: int = 10 * 1024 * 1024

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "timeout_s": self.timeout_s,
            "max_dim_px": self.max_dim_px,
            "ocr_enabled": self.ocr_enabled,
            "max_bytes": self.max_bytes,
        }


def load_vision_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> VisionConfig:
    source = dict(env) if env is not None else dict(os.environ)
    merged: Dict[str, Any] = dict(_DEFAULTS)
    for env_key, field_name in _ENV_MAP:
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
    try:
        timeout = float(merged.get("timeout_s", 60.0))
    except (TypeError, ValueError):
        timeout = 60.0
    timeout = min(300.0, max(5.0, timeout))
    try:
        max_dim = int(merged.get("max_dim_px", 1280))
    except (TypeError, ValueError):
        max_dim = 1280
    max_dim = min(4096, max(256, max_dim))
    try:
        max_bytes = int(merged.get("max_bytes", 10 * 1024 * 1024))
    except (TypeError, ValueError):
        max_bytes = 10 * 1024 * 1024
    max_bytes = min(50 * 1024 * 1024, max(256 * 1024, max_bytes))
    return VisionConfig(
        model=str(merged.get("model", "") or ""),
        timeout_s=timeout,
        max_dim_px=max_dim,
        ocr_enabled=_as_bool(merged.get("ocr_enabled", True)),
        max_bytes=max_bytes,
    )
