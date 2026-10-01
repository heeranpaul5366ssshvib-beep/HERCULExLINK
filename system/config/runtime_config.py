from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Runtime Configuration (v1.0)
Author: Heeran Paul
License: MIT
--------------------------------------------

Central operator configuration, following the embedding_config /
semantic_config conventions: explicit dict > HERCULE_* env vars >
safe defaults. No API keys are required for the local Ollama path.

Invalid values fail clearly with field/reason/code instead of
silently degrading. Existing per-module env reads delegate here so
documented behavior stays identical.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

_DEFAULTS: Dict[str, Any] = {
    "ollama_host": "http://127.0.0.1:11434",
    "default_model": "llama3",
    "ollama_timeout_s": 120.0,
    "allow_mock_fallback": False,
    "cognitive_planning": "auto",
    "planning_timeout_s": 80.0,
    "task_store": "",
    "memory_dir": "",
    "experience_store": "",
    "skills_store": "",
    "autonomy_enabled": False,
    "autonomy_poll_interval_s": 1.0,
    "autonomy_max_task_runtime_s": 300.0,
    "autonomy_max_concurrent_tasks": 1,
    "debug_raw": False,
    "model_provider": "auto",
    "model_path": "",
    "offline": False,
    "native_model_path": "",
    "native_tokenizer_dir": "",
}

_ENV_MAP = (
    ("HERCULE_OLLAMA_HOST", "ollama_host"),
    ("HERCULE_DEFAULT_MODEL", "default_model"),
    ("HERCULE_OLLAMA_TIMEOUT", "ollama_timeout_s"),
    ("HERCULE_ALLOW_MOCK", "allow_mock_fallback"),
    ("HERCULE_COGNITIVE_PLANNING", "cognitive_planning"),
    ("HERCULE_PLANNING_TIMEOUT_S", "planning_timeout_s"),
    ("HERCULE_TASK_STORE", "task_store"),
    ("HERCULE_MEMORY_DIR", "memory_dir"),
    ("HERCULE_EXPERIENCE_STORE", "experience_store"),
    ("HERCULE_SKILLS_STORE", "skills_store"),
    ("HERCULE_AUTONOMY_ENABLED", "autonomy_enabled"),
    ("HERCULE_AUTONOMY_POLL_S", "autonomy_poll_interval_s"),
    ("HERCULE_AUTONOMY_MAX_RUNTIME_S", "autonomy_max_task_runtime_s"),
    ("HERCULE_AUTONOMY_MAX_CONCURRENT", "autonomy_max_concurrent_tasks"),
    ("HERCULE_AUTONOMY_LEVEL", "autonomy_level"),
    ("HERCULE_DEBUG_RAW", "debug_raw"),
    ("HERCULE_MODEL_PROVIDER", "model_provider"),
    ("HERCULE_MODEL_PATH", "model_path"),
    ("HERCULE_OFFLINE", "offline"),
    ("HERCULE_NATIVE_MODEL_PATH", "native_model_path"),
    ("HERCULE_NATIVE_TOKENIZER_DIR", "native_tokenizer_dir"),
)


class RuntimeConfigError(ValueError):
    """Structured configuration error with field/reason/code."""

    def __init__(self, field: str, reason: str, code: str = "RUNTIME_CONFIG_INVALID"):
        super().__init__(f"runtime config invalid [{field}]: {reason} ({code})")
        self.field = field
        self.reason = reason
        self.code = code


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class RuntimeConfig:
    ollama_host: str = "http://127.0.0.1:11434"
    default_model: str = "llama3"
    ollama_timeout_s: float = 120.0
    allow_mock_fallback: bool = False
    cognitive_planning: str = "auto"
    planning_timeout_s: float = 80.0
    task_store: str = ""
    memory_dir: str = ""
    experience_store: str = ""  # explicit experiences.json path (UAI L3)
    skills_store: str = ""  # explicit skills.json path (UAI L3)
    autonomy_enabled: bool = False
    autonomy_poll_interval_s: float = 1.0
    autonomy_max_task_runtime_s: float = 300.0
    autonomy_max_concurrent_tasks: int = 1
    autonomy_level: int = 2
    debug_raw: bool = False
    model_provider: str = "auto"  # auto | builtin | ollama | native (v2, additive)
    model_path: str = ""  # explicit GGUF path (v2, additive)
    offline: bool = False  # no external model APIs (v2, additive)
    native_model_path: str = ""  # explicit native checkpoint path (N9, additive)
    native_tokenizer_dir: str = ""  # explicit native tokenizer path (N9, additive)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ollama_host": self.ollama_host,
            "default_model": self.default_model,
            "ollama_timeout_s": self.ollama_timeout_s,
            "allow_mock_fallback": self.allow_mock_fallback,
            "cognitive_planning": self.cognitive_planning,
            "planning_timeout_s": self.planning_timeout_s,
            "task_store": self.task_store,
            "memory_dir": self.memory_dir,
            "experience_store": self.experience_store,
            "skills_store": self.skills_store,
            "autonomy_enabled": self.autonomy_enabled,
            "autonomy_poll_interval_s": self.autonomy_poll_interval_s,
            "autonomy_max_task_runtime_s": self.autonomy_max_task_runtime_s,
            "autonomy_max_concurrent_tasks": self.autonomy_max_concurrent_tasks,
            "autonomy_level": self.autonomy_level,
            "debug_raw": self.debug_raw,
            "model_provider": self.model_provider,
            "model_path": self.model_path,
            "offline": self.offline,
            "native_model_path": self.native_model_path,
            "native_tokenizer_dir": self.native_tokenizer_dir,
        }


def load_runtime_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> RuntimeConfig:
    """Build configuration: explicit dict > env vars > safe defaults."""
    source = dict(env) if env is not None else dict(os.environ)
    merged: Dict[str, Any] = dict(_DEFAULTS)
    for env_key, field_name in _ENV_MAP:
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})

    host = str(merged.get("ollama_host", "")).strip()
    if not host:
        raise RuntimeConfigError("ollama_host", "must be a non-empty URL")
    model = str(merged.get("default_model", "")).strip()
    if not model:
        raise RuntimeConfigError("default_model", "must be a non-empty model name")
    mode = str(merged.get("cognitive_planning", "auto")).strip().lower()
    # Unknown modes fall through to automatic selection (never crash
    # production on a typo); only explicit always/never override.
    if mode not in ("auto", "always", "never"):
        mode = "auto"
    try:
        ollama_timeout = float(merged.get("ollama_timeout_s", 120.0))
        planning_timeout = float(merged.get("planning_timeout_s", 80.0))
        poll_interval = float(merged.get("autonomy_poll_interval_s", 1.0))
        max_runtime = float(merged.get("autonomy_max_task_runtime_s", 300.0))
        max_concurrent = int(merged.get("autonomy_max_concurrent_tasks", 1))
    except (TypeError, ValueError):
        raise RuntimeConfigError("numeric", "timeout/interval/runtime/concurrent must be numeric")
    if ollama_timeout <= 0:
        raise RuntimeConfigError("ollama_timeout_s", "must be positive")
    if planning_timeout <= 0:
        raise RuntimeConfigError("planning_timeout_s", "must be positive")
    if poll_interval <= 0:
        raise RuntimeConfigError("autonomy_poll_interval_s", "must be positive")
    if max_runtime <= 0:
        raise RuntimeConfigError("autonomy_max_task_runtime_s", "must be positive")
    if max_concurrent < 1:
        raise RuntimeConfigError("autonomy_max_concurrent_tasks", "must be >= 1")
    try:
        autonomy_level = int(merged.get("autonomy_level", 2))
    except (TypeError, ValueError):
        raise RuntimeConfigError("autonomy_level", "must be an integer 0-5")
    if not 0 <= autonomy_level <= 5:
        raise RuntimeConfigError("autonomy_level", "must be an integer 0-5")
    provider = str(merged.get("model_provider", "auto")).strip().lower()
    # Unknown providers fall through to automatic selection (never crash
    # production on a typo); only explicit builtin/ollama override.
    if provider not in ("auto", "builtin", "ollama"):
        provider = "auto"
    return RuntimeConfig(
        ollama_host=host,
        default_model=model,
        ollama_timeout_s=ollama_timeout,
        allow_mock_fallback=_as_bool(merged.get("allow_mock_fallback", False)),
        cognitive_planning=mode,
        planning_timeout_s=planning_timeout,
        task_store=str(merged.get("task_store", "") or ""),
        memory_dir=str(merged.get("memory_dir", "") or ""),
        experience_store=str(merged.get("experience_store", "") or ""),
        skills_store=str(merged.get("skills_store", "") or ""),
        autonomy_enabled=_as_bool(merged.get("autonomy_enabled", False)),
        autonomy_poll_interval_s=poll_interval,
        autonomy_max_task_runtime_s=max_runtime,
        autonomy_max_concurrent_tasks=max_concurrent,
        autonomy_level=autonomy_level,
        debug_raw=_as_bool(merged.get("debug_raw", False)),
        model_provider=provider,
        model_path=str(merged.get("model_path", "") or ""),
        offline=_as_bool(merged.get("offline", False)),
    )
