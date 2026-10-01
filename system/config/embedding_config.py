from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Embedding Configuration
Author: Heeran Paul
License: MIT
--------------------------------------------

Configuration-driven embedding provider selection. Precedence:

explicit dict > HERCULE_EMBEDDING_* env vars > mode defaults

Modes:

PRODUCTION  real providers only; test-only backends fail closed, even
            when explicitly configured. No silent substitution.
TEST        hermetic deterministic provider (hash), fast, offline.
CI          like TEST, forced regardless of configured provider.
OFFLINE     no network: cached real weights when loadable, else the
            configured fallback, else clear failure.
SIMULATION  deterministic provider for demos/fixtures.

Selection order is explicit: configured provider -> validate -> health
check -> use; configured fallback (same steps) -> use; otherwise fail
clearly with a structured ``EmbeddingConfigError``.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

KNOWN_PROVIDERS = ("sentence-transformers", "ollama", "hash")

_VALID_DEVICES = ("cpu", "auto", "cuda", "mps", "ollama-server")
_VALID_DEVICE_PREFIXES = ("cuda:", "mps:", "cpu:")


class EmbeddingMode(str, Enum):
    PRODUCTION = "production"
    TEST = "test"
    CI = "ci"
    OFFLINE = "offline"
    SIMULATION = "simulation"


class EmbeddingConfigError(ValueError):
    """Structured configuration error: ``field``, ``reason``, ``code``."""

    def __init__(self, field: str, reason: str, code: str = "EMBEDDING_CONFIG_INVALID"):
        super().__init__(f"embedding config invalid [{field}]: {reason} ({code})")
        self.field = field
        self.reason = reason
        self.code = code


@dataclass
class EmbeddingConfig:
    provider: str = "sentence-transformers"
    model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 0  # 0 = accept whatever the provider declares
    normalized: Optional[bool] = None  # None = accept provider default
    device: str = "cpu"
    batch_size: int = 32
    cache: bool = True
    cache_version: str = "1"
    fallback_provider: str = ""
    fallback_model_id: str = ""
    mode: EmbeddingMode = EmbeddingMode.PRODUCTION
    allow_test_providers: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "dimension": self.dimension,
            "normalized": self.normalized,
            "device": self.device,
            "batch_size": self.batch_size,
            "cache": self.cache,
            "cache_version": self.cache_version,
            "fallback_provider": self.fallback_provider,
            "fallback_model_id": self.fallback_model_id,
            "mode": self.mode.value if isinstance(self.mode, EmbeddingMode) else str(self.mode),
            "allow_test_providers": self.allow_test_providers,
        }


_MODE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "production": {"provider": "sentence-transformers", "model_id": "sentence-transformers/all-MiniLM-L6-v2"},
    "test": {"provider": "hash", "model_id": "hercule-hash-test-v1", "allow_test_providers": True},
    "ci": {"provider": "hash", "model_id": "hercule-hash-test-v1", "allow_test_providers": True},
    "offline": {"provider": "sentence-transformers", "model_id": "sentence-transformers/all-MiniLM-L6-v2"},
    "simulation": {"provider": "hash", "model_id": "hercule-hash-test-v1", "allow_test_providers": True},
}

_ENV_MAP = (
    ("HERCULE_MODE", "mode"),
    ("HERCULE_EMBEDDING_PROVIDER", "provider"),
    ("HERCULE_EMBEDDING_MODEL", "model_id"),
    ("HERCULE_EMBEDDING_DIMENSION", "dimension"),
    ("HERCULE_EMBEDDING_DEVICE", "device"),
    ("HERCULE_EMBEDDING_BATCH_SIZE", "batch_size"),
    ("HERCULE_EMBEDDING_FALLBACK", "fallback_provider"),
    ("HERCULE_EMBEDDING_FALLBACK_MODEL", "fallback_model_id"),
)


def load_embedding_config(
    overrides: Optional[Dict[str, Any]] = None,
    env: Optional[Dict[str, str]] = None,
) -> EmbeddingConfig:
    """Build config: explicit dict > env vars > mode defaults."""
    source = dict(env) if env is not None else dict(os.environ)
    raw_mode = str((overrides or {}).get("mode") or source.get("HERCULE_MODE", "production")).lower()
    try:
        mode = EmbeddingMode(raw_mode)
    except ValueError:
        raise EmbeddingConfigError("mode", f"unknown mode '{raw_mode}'", "EMBEDDING_UNKNOWN_MODE")
    merged: Dict[str, Any] = dict(_MODE_DEFAULTS[mode.value])
    for env_key, field_name in _ENV_MAP:
        if field_name == "mode":
            continue
        value = source.get(env_key)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
    merged["mode"] = mode
    merged["mode"] = mode
    for int_field in ("dimension", "batch_size"):
        try:
            merged[int_field] = int(merged.get(int_field, getattr(EmbeddingConfig, int_field)))
        except (TypeError, ValueError):
            raise EmbeddingConfigError(int_field, f"must be an integer, got {merged.get(int_field)!r}")
    for bool_field in ("cache", "allow_test_providers"):
        value = merged.get(bool_field, getattr(EmbeddingConfig, bool_field))
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "on")
        merged[bool_field] = bool(value)
    normalized = merged.get("normalized", None)
    if isinstance(normalized, str):
        normalized = normalized.strip().lower() in ("1", "true", "yes", "on")
    merged["normalized"] = normalized
    if mode == EmbeddingMode.CI:
        # CI is always hermetic, regardless of what was configured.
        merged["provider"] = "hash"
        merged["model_id"] = "hercule-hash-test-v1"
        merged["allow_test_providers"] = True
    return EmbeddingConfig(**{k: merged.get(k, getattr(EmbeddingConfig, k, None)) for k in EmbeddingConfig.__dataclass_fields__})


def validate_device(device: str) -> None:
    if device in _VALID_DEVICES or any(device.startswith(prefix) for prefix in _VALID_DEVICE_PREFIXES):
        return
    raise EmbeddingConfigError("device", f"unsupported device '{device}'", "EMBEDDING_BAD_DEVICE")


def build_provider(provider_name: str, model_id: str, device: str = "cpu", batch_size: int = 32):
    """Instantiate (not health-check) a provider by name."""
    if provider_name == "sentence-transformers":
        from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider

        return SentenceTransformerEmbeddingProvider(model_id=model_id, device=None if device == "auto" else device, batch_size=batch_size)
    if provider_name == "ollama":
        from models.embeddings.ollama_provider import OllamaEmbeddingProvider

        return OllamaEmbeddingProvider(model_id=model_id)
    if provider_name == "hash":
        from models.embeddings.hash_provider import HashEmbeddingProvider

        return HashEmbeddingProvider(model_id=model_id or "hercule-hash-test-v1")
    raise EmbeddingConfigError("provider", f"nonexistent provider '{provider_name}'", "EMBEDDING_UNKNOWN_PROVIDER")


def validate_provider_config(provider, config: EmbeddingConfig, role: str = "provider") -> Dict[str, Any]:
    """Static validation before any health check. Raises on mismatch."""
    prefix = role
    if config.dimension and provider.dimension and config.dimension != provider.dimension:
        raise EmbeddingConfigError(
            f"{prefix}.dimension",
            f"configured dim {config.dimension} != provider dim {provider.dimension}",
            "EMBEDDING_DIMENSION_MISMATCH",
        )
    if config.normalized is not None and bool(config.normalized) != bool(provider.normalized):
        raise EmbeddingConfigError(
            f"{prefix}.normalized",
            f"configured normalized={config.normalized} != provider {provider.normalized}",
            "EMBEDDING_NORMALIZATION_MISMATCH",
        )
    if getattr(provider, "test_only", False):
        mode_allows = config.allow_test_providers or config.mode in (
            EmbeddingMode.TEST,
            EmbeddingMode.CI,
            EmbeddingMode.OFFLINE,
            EmbeddingMode.SIMULATION,
        )
        if not mode_allows:
            raise EmbeddingConfigError(
                f"{prefix}.provider",
                "test-only provider is not allowed by this configuration",
                "EMBEDDING_TEST_PROVIDER_BLOCKED",
            )
    validate_device(config.device)
    if not config.model_id:
        raise EmbeddingConfigError(f"{prefix}.model_id", "model id must not be empty", "EMBEDDING_BAD_MODEL")
    return {"model_id": provider.model_id, "dimension": provider.dimension, "normalized": provider.normalized}


def _mode_allows_test(config: EmbeddingConfig) -> bool:
    return config.allow_test_providers or config.mode in (
        EmbeddingMode.TEST,
        EmbeddingMode.CI,
        EmbeddingMode.OFFLINE,
        EmbeddingMode.SIMULATION,
    )


def resolve_embedding_provider(
    config: EmbeddingConfig,
    tracer=None,
    correlation_id: str = "",
    check_health: bool = True,
) -> Tuple[Any, Dict[str, Any]]:
    """Configured provider -> validate -> health -> use, else fallback, else fail.

    Returns (provider, report). The report records every step for
    RequestTrace; test-only providers in PRODUCTION fail closed.
    With ``check_health=False`` only static validation runs (no model
    loads) and the report marks health as unchecked.
    """
    from system.observability.trace import trace_embedding

    report: Dict[str, Any] = {"mode": config.mode.value, "attempts": [], "selected": None, "fallback_used": False}
    candidates = [(config.provider, config.model_id, False)]
    if config.fallback_provider:
        candidates.append((config.fallback_provider, config.fallback_model_id or config.model_id, True))

    last_error: Optional[Exception] = None
    fatal_codes = {
        "EMBEDDING_DIMENSION_MISMATCH",
        "EMBEDDING_NORMALIZATION_MISMATCH",
        "EMBEDDING_TEST_PROVIDER_BLOCKED",
        "EMBEDDING_BAD_MODEL",
        "EMBEDDING_BAD_DEVICE",
    }
    for provider_name, model_id, is_fallback in candidates:
        attempt: Dict[str, Any] = {"provider": provider_name, "model_id": model_id, "fallback": is_fallback}
        try:
            if provider_name not in KNOWN_PROVIDERS:
                raise EmbeddingConfigError("provider", f"nonexistent provider '{provider_name}'", "EMBEDDING_UNKNOWN_PROVIDER")
            provider = build_provider(provider_name, model_id, config.device, config.batch_size)
            if getattr(provider, "test_only", False) and not _mode_allows_test(config):
                raise EmbeddingConfigError(
                    "provider",
                    f"test-only provider '{provider_name}' cannot enter production",
                    "EMBEDDING_TEST_PROVIDER_BLOCKED",
                )
            validate_provider_config(provider, config, "fallback" if is_fallback else "provider")
            if not check_health:
                attempt["health"] = {"status": "unchecked", "available": "unchecked", "dimension": provider.dimension}
                attempt["selected"] = True
                report["attempts"].append(attempt)
                report["selected"] = {"provider": provider_name, "model_id": provider.model_id,
                                      "dimension": provider.dimension, "fallback": is_fallback}
                report["fallback_used"] = is_fallback
                report["health_checked"] = False
                return provider, report
            health = provider.health()
            attempt["health"] = {k: health.get(k) for k in ("status", "available", "dimension")}
            if not health.get("available", False):
                raise EmbeddingConfigError(
                    "provider" if not is_fallback else "fallback_provider",
                    f"backend '{provider_name}:{model_id}' unavailable: {health.get('reason', 'health check failed')}",
                    "EMBEDDING_BACKEND_UNAVAILABLE",
                )
            # Post-load check: dimensions unknown before load must match now.
            if config.dimension and provider.dimension and config.dimension != provider.dimension:
                raise EmbeddingConfigError(
                    "dimension",
                    f"configured dim {config.dimension} != loaded model dim {provider.dimension}",
                    "EMBEDDING_DIMENSION_MISMATCH",
                )
            attempt["selected"] = True
            report["attempts"].append(attempt)
            report["selected"] = {"provider": provider_name, "model_id": provider.model_id,
                                  "dimension": provider.dimension, "fallback": is_fallback}
            report["fallback_used"] = is_fallback
            if tracer is not None:
                trace_embedding(tracer, correlation_id or "embedding-startup", provider.model_id,
                                provider.dimension, 0, 0.0, False, ["provider-selection"])
            report["health_checked"] = True
            return provider, report
        except Exception as exc:
            attempt["selected"] = False
            attempt["error"] = str(exc)
            attempt["code"] = getattr(exc, "code", type(exc).__name__)
            report["attempts"].append(attempt)
            last_error = exc
            if getattr(exc, "code", "") in fatal_codes:
                # Configuration errors would break the fallback identically:
                # fail fast instead of masking them behind NO_BACKEND.
                raise
    if len(candidates) == 1 and isinstance(last_error, EmbeddingConfigError):
        # No fallback configured: surface the specific validation error.
        raise last_error
    raise EmbeddingConfigError(
        "provider",
        f"no usable embedding backend (tried {[c[0] for c in candidates]}): {last_error}",
        "EMBEDDING_NO_BACKEND",
    )


def default_providers_for_mode(mode: str) -> List[str]:
    """Documented selection order per mode (highest priority first)."""
    table = {
        "production": ["sentence-transformers", "ollama"],
        "test": ["hash"],
        "ci": ["hash"],
        "offline": ["sentence-transformers", "hash"],
        "simulation": ["hash"],
    }
    return list(table.get(mode, ["sentence-transformers"]))
