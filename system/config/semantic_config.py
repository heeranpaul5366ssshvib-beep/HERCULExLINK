from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Semantic Inference Configuration
Author: Heeran Paul
License: MIT
--------------------------------------------

Feature flags for model-backed capability inference, following the
embedding_config conventions: explicit dict > HERCULE_SEMANTIC_* env
> safe defaults. Default production behavior is SEMANTIC_OPTIONAL
(deterministic always runs; semantic may add validated candidates).

Semantic inference never becomes mandatory silently: required=True
and cache use are opt-in, and invalid configuration fails clearly.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from cognition.capabilities.hybrid import HybridMode

_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "mode": "semantic_optional",
    "shadow": False,
    "required": False,
    "timeout_s": 0.0,
    "min_confidence": 0.5,
    "low_confidence": "retain-optional",
    "max_retries": 1,
    "cache_enabled": False,
    "model": "",
}

_ENV_MAP = (
    ("HERCULE_SEMANTIC_ENABLED", "enabled"),
    ("HERCULE_SEMANTIC_MODE", "mode"),
    ("HERCULE_SEMANTIC_SHADOW", "shadow"),
    ("HERCULE_SEMANTIC_REQUIRED", "required"),
    ("HERCULE_SEMANTIC_TIMEOUT", "timeout_s"),
    ("HERCULE_SEMANTIC_CONFIDENCE", "min_confidence"),
    ("HERCULE_SEMANTIC_LOW_CONFIDENCE", "low_confidence"),
    ("HERCULE_SEMANTIC_RETRIES", "max_retries"),
    ("HERCULE_SEMANTIC_CACHE", "cache_enabled"),
    ("HERCULE_SEMANTIC_MODEL", "model"),
)


class SemanticConfigError(ValueError):
    """Structured flag error with field/reason/code."""

    def __init__(self, field: str, reason: str, code: str = "SEMANTIC_CONFIG_INVALID"):
        super().__init__(f"semantic config invalid [{field}]: {reason} ({code})")
        self.field = field
        self.reason = reason
        self.code = code


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class SemanticConfig:
    enabled: bool = False
    mode: HybridMode = HybridMode.SEMANTIC_OPTIONAL
    shadow: bool = False
    required: bool = False
    timeout_s: float = 0.0
    min_confidence: float = 0.5
    low_confidence: str = "retain-optional"
    max_retries: int = 1
    cache_enabled: bool = False
    model: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode.value if isinstance(self.mode, HybridMode) else str(self.mode),
            "shadow": self.shadow, "required": self.required,
            "timeout_s": self.timeout_s, "min_confidence": self.min_confidence,
            "low_confidence": self.low_confidence, "max_retries": self.max_retries,
            "cache_enabled": self.cache_enabled, "model": self.model,
        }


def load_semantic_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> SemanticConfig:
    """Build flags: explicit dict > env vars > safe defaults."""
    source = dict(env) if env is not None else dict(os.environ)
    merged: Dict[str, Any] = dict(_DEFAULTS)
    for env_key, field_name in _ENV_MAP:
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})

    try:
        mode = HybridMode(str(merged.get("mode", "semantic_optional")).lower())
    except ValueError:
        raise SemanticConfigError("mode", f"unknown mode {merged.get('mode')!r}", "SEMANTIC_UNKNOWN_MODE")
    low = str(merged.get("low_confidence", "retain-optional")).lower()
    if low not in ("retain-optional", "reject", "fallback"):
        raise SemanticConfigError("low_confidence", f"unknown policy {low!r}")
    try:
        timeout_s = float(merged.get("timeout_s", 0.0))
        min_confidence = float(merged.get("min_confidence", 0.5))
        max_retries = int(merged.get("max_retries", 1))
    except (TypeError, ValueError):
        raise SemanticConfigError("numeric", "timeout/confidence/retries must be numeric")
    if not 0.0 <= min_confidence <= 1.0:
        raise SemanticConfigError("min_confidence", "must be within 0.0..1.0")
    if max_retries < 0 or max_retries > 5:
        raise SemanticConfigError("max_retries", "must be within 0..5")
    if timeout_s < 0:
        raise SemanticConfigError("timeout_s", "must not be negative")
    return SemanticConfig(
        enabled=_as_bool(merged.get("enabled", False)), mode=mode,
        shadow=_as_bool(merged.get("shadow", False)), required=_as_bool(merged.get("required", False)),
        timeout_s=timeout_s, min_confidence=min_confidence, low_confidence=low,
        max_retries=max_retries, cache_enabled=_as_bool(merged.get("cache_enabled", False)),
        model=str(merged.get("model", "")),
    )


def apply_to_proposer(proposer: Any, config: SemanticConfig) -> Any:
    """Push flags onto a SemanticCapabilityProposer (same process)."""
    proposer.enabled = config.enabled
    proposer.shadow = config.shadow or config.mode == HybridMode.SHADOW
    proposer.required = config.required
    proposer.min_confidence = config.min_confidence
    proposer.low_confidence = config.low_confidence
    proposer.max_retries = config.max_retries
    proposer.timeout_s = config.timeout_s or None
    return proposer


def mode_for_config(config: SemanticConfig) -> HybridMode:
    """Effective resolution mode (explicit shadow wins)."""
    if config.shadow:
        return HybridMode.SHADOW
    return config.mode
