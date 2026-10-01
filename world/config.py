from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: World Model Configuration (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


_ENV_MAP = (
    ("HERCULE_WORLD_PATH", "store_path"),
    ("HERCULE_WORLD_MAX_ENTITIES", "max_entities"),
    ("HERCULE_WORLD_MAX_OBSERVATIONS", "max_observations"),
    ("HERCULE_WORLD_STALE_AFTER_S", "stale_after_s"),
)

_DEFAULTS: Dict[str, Any] = {
    "store_path": "",
    "max_entities": 500,
    "max_observations": 1000,
    "stale_after_s": 86400.0,
}


@dataclass
class WorldConfig:
    store_path: str = ""
    max_entities: int = 500
    max_observations: int = 1000
    stale_after_s: float = 86400.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "store_path": self.store_path,
            "max_entities": self.max_entities,
            "max_observations": self.max_observations,
            "stale_after_s": self.stale_after_s,
        }


def load_world_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> WorldConfig:
    source = dict(env) if env is not None else dict(os.environ)
    merged: Dict[str, Any] = dict(_DEFAULTS)
    for env_key, field_name in _ENV_MAP:
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})

    def _int(key: str, default: int, lo: int, hi: int) -> int:
        try:
            value = int(merged.get(key, default))
        except (TypeError, ValueError):
            value = default
        return min(hi, max(lo, value))

    try:
        stale = float(merged.get("stale_after_s", 86400.0))
    except (TypeError, ValueError):
        stale = 86400.0
    return WorldConfig(
        store_path=str(merged.get("store_path", "") or ""),
        max_entities=_int("max_entities", 500, 10, 10000),
        max_observations=_int("max_observations", 1000, 10, 20000),
        stale_after_s=min(86400.0 * 30, max(60.0, stale)),
    )


def default_store_path(config: Optional[WorldConfig] = None) -> str:
    """Frozen-aware world-store location (user data, never Program Files)."""
    if config is not None and config.store_path:
        return config.store_path
    from system.paths import resolve_data_path

    return resolve_data_path("data/world/hercule_world.json")
