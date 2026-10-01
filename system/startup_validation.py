from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Startup Validation
Author: Heeran Paul
License: MIT
--------------------------------------------

Fail-fast startup gate for the embedding subsystem. Distinguishes:

CONFIGURATION ERROR  invalid provider/model/dim/device/normalization
BACKEND UNAVAILABLE  valid config, backend down or missing weights
RUNTIME FAILURE      unexpected errors during validation

Raises ``StartupValidationError`` (carrying ``failure_class``) before
the system accepts work. Pure validation otherwise.
"""

from typing import Any, Dict, Optional, Tuple

from system.config.embedding_config import (
    EmbeddingConfigError,
    load_embedding_config,
    resolve_embedding_provider,
)

CONFIGURATION_ERROR = "configuration_error"
BACKEND_UNAVAILABLE = "backend_unavailable"
RUNTIME_FAILURE = "runtime_failure"

_CONFIG_CODES = {
    "EMBEDDING_CONFIG_INVALID",
    "EMBEDDING_UNKNOWN_MODE",
    "EMBEDDING_UNKNOWN_PROVIDER",
    "EMBEDDING_BAD_DEVICE",
    "EMBEDDING_BAD_MODEL",
    "EMBEDDING_DIMENSION_MISMATCH",
    "EMBEDDING_NORMALIZATION_MISMATCH",
    "EMBEDDING_TEST_PROVIDER_BLOCKED",
}

_BACKEND_CODES = {
    "EMBEDDING_BACKEND_UNAVAILABLE",
    "EMBEDDING_NO_BACKEND",
}


class StartupValidationError(EmbeddingConfigError):
    """Startup gate failure with a ``failure_class`` for operators."""

    def __init__(self, failure_class: str, field: str, reason: str, code: str):
        super().__init__(field, f"[{failure_class}] {reason}", code)
        self.failure_class = failure_class


def classify_startup_error(exc: Exception) -> str:
    code = getattr(exc, "code", "")
    if code in _CONFIG_CODES:
        return CONFIGURATION_ERROR
    if code in _BACKEND_CODES:
        return BACKEND_UNAVAILABLE
    return RUNTIME_FAILURE


def validate_startup(
    config_like: Any = None,
    tracer=None,
    correlation_id: str = "startup",
    check_health: bool = True,
) -> Tuple[Any, Dict[str, Any]]:
    """Validate embedding config; fail fast with a classified error."""
    try:
        config = config_like if hasattr(config_like, "provider") else load_embedding_config(dict(config_like or {}))
        provider, report = resolve_embedding_provider(
            config, tracer=tracer, correlation_id=correlation_id, check_health=check_health
        )
        report["failure_class"] = None
        return provider, report
    except Exception as exc:
        failure_class = classify_startup_error(exc) if isinstance(exc, EmbeddingConfigError) else RUNTIME_FAILURE
        raise StartupValidationError(
            failure_class,
            getattr(exc, "field", "provider"),
            str(exc),
            getattr(exc, "code", type(exc).__name__),
        )
