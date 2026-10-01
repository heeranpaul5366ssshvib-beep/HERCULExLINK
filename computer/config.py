from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Computer-Use Configuration (v1.2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Explicit dict > HERCULE_COMPUTER_* env vars > safe defaults. Computer
control is OFF by default (opt-in): nothing moves the pointer, clicks,
or types unless the operator enables it. All bounds prevent runaway
control loops. No API keys, no cloud.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


_ENV_MAP = (
    ("HERCULE_COMPUTER_ENABLED", "enabled"),
    ("HERCULE_COMPUTER_MAX_ACTIONS", "max_actions"),
    ("HERCULE_COMPUTER_MAX_RETRIES", "max_retries"),
    ("HERCULE_COMPUTER_MAX_REPLANS", "max_replans"),
    ("HERCULE_COMPUTER_MAX_RUNTIME_S", "max_runtime_s"),
    ("HERCULE_COMPUTER_ACTION_TIMEOUT_S", "action_timeout_s"),
    ("HERCULE_COMPUTER_OBSERVATION_MAX_AGE_S", "observation_max_age_s"),
    ("HERCULE_COMPUTER_APPROVAL_TIMEOUT_S", "approval_timeout_s"),
    ("HERCULE_COMPUTER_ALLOWED_APPS", "allowed_apps"),
)

_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "max_actions": 10,
    "max_retries": 2,
    "max_replans": 1,
    "max_runtime_s": 120.0,
    "action_timeout_s": 15.0,
    "observation_max_age_s": 30.0,
    "approval_timeout_s": 120.0,
    "allowed_apps": "notepad,calc",
}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class ComputerConfig:
    enabled: bool = False
    max_actions: int = 10
    max_retries: int = 2
    max_replans: int = 1
    max_runtime_s: float = 120.0
    action_timeout_s: float = 15.0
    observation_max_age_s: float = 30.0
    approval_timeout_s: float = 120.0
    allowed_apps: List[str] = field(default_factory=lambda: ["notepad", "calc"])

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_actions": self.max_actions,
            "max_retries": self.max_retries,
            "max_replans": self.max_replans,
            "max_runtime_s": self.max_runtime_s,
            "action_timeout_s": self.action_timeout_s,
            "observation_max_age_s": self.observation_max_age_s,
            "approval_timeout_s": self.approval_timeout_s,
            "allowed_apps": list(self.allowed_apps),
        }


def load_computer_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> ComputerConfig:
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

    def _float(key: str, default: float, lo: float, hi: float) -> float:
        try:
            value = float(merged.get(key, default))
        except (TypeError, ValueError):
            value = default
        return min(hi, max(lo, value))

    raw_apps = merged.get("allowed_apps", "notepad,calc")
    if isinstance(raw_apps, str):
        allowed = [a.strip().lower() for a in raw_apps.split(",") if a.strip()]
    else:
        allowed = [str(a).strip().lower() for a in (raw_apps or []) if str(a).strip()]
    return ComputerConfig(
        enabled=_as_bool(merged.get("enabled", False)),
        max_actions=_int("max_actions", 10, 1, 50),
        max_retries=_int("max_retries", 2, 0, 5),
        max_replans=_int("max_replans", 1, 0, 3),
        max_runtime_s=_float("max_runtime_s", 120.0, 10.0, 600.0),
        action_timeout_s=_float("action_timeout_s", 15.0, 2.0, 120.0),
        observation_max_age_s=_float("observation_max_age_s", 30.0, 5.0, 300.0),
        approval_timeout_s=_float("approval_timeout_s", 120.0, 10.0, 600.0),
        allowed_apps=allowed or ["notepad", "calc"],
    )
