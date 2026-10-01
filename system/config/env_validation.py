from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Environment Validation
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured, read-only environment diagnostics: Python version,
required/optional packages (with floor versions from
requirements.txt), embedding/vector backend availability, model
weights, devices, and embedding configuration validity.

Never installs anything. Heavy model loads happen only when
``check_models=True`` is passed explicitly.
"""

import importlib.metadata as metadata
import platform
import sys
from typing import Any, Dict, List, Optional

REQUIRED_PACKAGES = {
    "sentence-transformers": "5.1.0",
    "faiss-cpu": "1.12.0",
    "psutil": "7.0.0",
    "numpy": "2.3.0",
    "transformers": "4.55.0",
    "torch": "2.8.0",
    "pytest": "8.4.0",
    "pytest-asyncio": "1.1.0",
}

OPTIONAL_PACKAGES = {
    "ollama": "0.5.0",
    "chromadb": "1.0.0",
    "PyYAML": "6.0.0",
    "accelerate": "1.10.0",
    "tokenizers": "0.22.0",
}

MIN_PYTHON = (3, 11)


def _parse_version(text: str) -> tuple:
    parts = []
    for chunk in str(text).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_python() -> Dict[str, Any]:
    current = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    ok = (sys.version_info.major, sys.version_info.minor) >= MIN_PYTHON
    return {"current": ".".join(map(str, current)), "minimum": ".".join(map(str, MIN_PYTHON)),
            "ok": ok, "platform": platform.platform()}


def check_package(name: str, minimum: str, required: bool = True) -> Dict[str, Any]:
    try:
        version = metadata.version(name)
    except Exception:
        return {"name": name, "required": required, "installed": False, "version": "",
                "minimum": minimum, "ok": not required, "detail": "not installed"}
    ok = _parse_version(version) >= _parse_version(minimum)
    return {"name": name, "required": required, "installed": True, "version": version,
            "minimum": minimum, "ok": ok,
            "detail": "" if ok else f"version {version} below floor {minimum}"}


def check_packages() -> List[Dict[str, Any]]:
    entries = [check_package(name, floor, True) for name, floor in REQUIRED_PACKAGES.items()]
    entries += [check_package(name, floor, False) for name, floor in OPTIONAL_PACKAGES.items()]
    return entries


def check_vector_backend() -> Dict[str, Any]:
    try:
        from memory.vector.faiss_adapter import _HAS_FAISS

        faiss_present = bool(_HAS_FAISS)
    except Exception:
        faiss_present = False
    backends: Dict[str, Any] = {"faiss_present": faiss_present, "backends": {}}
    try:
        from memory.vector.vector_manager import VectorMemory

        for name in ("memory", "faiss" if faiss_present else "memory"):
            try:
                store = VectorMemory(dim=8, backend=name)
                backends["backends"][name] = {"constructible": True, "dim": store.dim}
            except Exception as exc:
                backends["backends"][name] = {"constructible": False, "error": str(exc)[:160]}
    except Exception as exc:
        backends["error"] = str(exc)[:200]
    backends["ok"] = bool(backends["backends"])
    return backends


def check_embedding_backends(check_models: bool = False) -> Dict[str, Any]:
    """Provider availability. Model loads only when check_models=True."""
    providers: Dict[str, Any] = {}
    try:
        from models.embeddings.hash_provider import HashEmbeddingProvider

        probe = HashEmbeddingProvider()
        providers["hash"] = {"available": probe.available(), "dimension": probe.dimension, "test_only": True}
    except Exception as exc:
        providers["hash"] = {"available": False, "error": str(exc)[:160]}
    try:
        from models.embeddings.ollama_provider import OllamaEmbeddingProvider

        probe = OllamaEmbeddingProvider()
        providers["ollama"] = {"available": probe.available(), "dimension": probe.dimension, "test_only": False}
    except Exception as exc:
        providers["ollama"] = {"available": False, "error": str(exc)[:160]}
    if check_models:
        try:
            from models.embeddings.sentence_transformer_provider import SentenceTransformerEmbeddingProvider

            probe = SentenceTransformerEmbeddingProvider()
            up = probe.available()
            providers["sentence-transformers"] = {
                "available": up, "dimension": probe.dimension if up else 0, "test_only": False,
            }
        except Exception as exc:
            providers["sentence-transformers"] = {"available": False, "error": str(exc)[:160]}
    else:
        providers["sentence-transformers"] = {"available": "unchecked", "detail": "pass check_models=True to load weights"}
    providers["ok"] = any(v.get("available") is True for v in providers.values())
    return providers


def check_devices() -> Dict[str, Any]:
    info: Dict[str, Any] = {"cpu": True, "cuda": False, "detail": ""}
    try:
        import torch

        info["cuda"] = bool(torch.cuda.is_available())
        info["detail"] = f"torch {torch.__version__}"
    except Exception as exc:
        info["detail"] = f"torch unavailable: {exc}"
    try:
        import psutil

        info["ram_gb"] = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except Exception:
        pass
    info["ok"] = True
    return info


def check_embedding_config(config_like: Any = None) -> Dict[str, Any]:
    """Static configuration validity (no model loads, no health probes)."""
    try:
        from system.config.embedding_config import load_embedding_config, validate_provider_config, build_provider
    except Exception as exc:
        return {"ok": False, "error": f"config module unavailable: {exc}"}
    try:
        config = config_like if hasattr(config_like, "provider") else load_embedding_config(dict(config_like or {}))
        provider = build_provider(config.provider, config.model_id, config.device, config.batch_size)
        validate_provider_config(provider, config)
        return {"ok": True, "mode": config.mode.value, "provider": config.provider,
                "model_id": config.model_id, "error": ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "code": getattr(exc, "code", type(exc).__name__)}


def validate_environment(config_like: Any = None, check_models: bool = False) -> Dict[str, Any]:
    """Full structured report. Pure diagnostics — installs nothing."""
    python = check_python()
    packages = check_packages()
    vectors = check_vector_backend()
    embeddings = check_embedding_backends(check_models)
    devices = check_devices()
    config = check_embedding_config(config_like)
    ok = (
        python["ok"]
        and all(p["ok"] for p in packages if p["required"])
        and vectors["ok"]
        and embeddings["ok"]
        and config["ok"]
    )
    return {
        "python": python,
        "packages": packages,
        "vector_backend": vectors,
        "embedding_backends": embeddings,
        "devices": devices,
        "embedding_config": config,
        "ok": ok,
    }
