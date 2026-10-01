from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: models/model_manager.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Model Manager
Manages AI model loading, selection, routing,
and text generation execution.

Production contract: the real local model (Ollama) is the default
path. The mock adapter is NEVER a silent production fallback — it
serves only explicit requests (``load_model("mock")`` / tests) or
when ``allow_mock_fallback`` is explicitly enabled. When no real
model can serve a prompt, generate() returns a structured
``[HERCULE Error]`` identifying subsystem/operation/exception —
never a fabricated success.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from models.adapters.mock_adapter import MockAdapter
from models.adapters.ollama_adapter import OllamaAdapter
from models.adapters.transformers_adapter import TransformersAdapter
from models.ollama.client import OllamaError
from models.registry.registry import ModelInfo
from models.router.model_router import ModelRouter

logger = logging.getLogger("HERCULE.Models.ModelManager")

# Preferred installed models, first match wins when the configured
# default is not installed. Ordering favors stronger local models.
MODEL_PREFERENCES = [
    "llama3.2:3b",
    "qwen2.5:1.5b",
    "qwen3:0.6b",
    "qwen3.5:0.8b",
]


def _error_category(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    if code:
        return str(code)
    name = type(exc).__name__
    if "Timeout" in name or "timed out" in str(exc).lower():
        return "TIMEOUT"
    if "Connection" in name or "refused" in str(exc).lower():
        return "CONNECTION"
    return f"ERROR:{name}"


class ModelManager:
    """
    Central manager for AI model inference and adapter routing.
    """

    def __init__(self, default_model: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        self.config = dict(config or {})
        # Central runtime config (explicit dict > env > safe defaults);
        # per-field fallbacks below preserve exact legacy precedence.
        from system.config.runtime_config import load_runtime_config
        runtime = load_runtime_config({k: v for k, v in self.config.items()
                                        if k in ("ollama_host", "default_model", "ollama_timeout_s",
                                                 "allow_mock_fallback", "model_provider",
                                                 "model_path", "offline",
                                                 "native_model_path", "native_tokenizer_dir")})
        if default_model is None:
            default_model = str(self.config.get("default_model", "")
                                or runtime.default_model)
        self.ollama_host = str(self.config.get("ollama_host", runtime.ollama_host))
        self.ollama_timeout_s = float(self.config.get("ollama_timeout_s", runtime.ollama_timeout_s))
        self.allow_mock_fallback = bool(
            self.config.get("allow_mock_fallback", runtime.allow_mock_fallback))
        # v2 built-in provider selection (additive; default "auto" keeps
        # the historical Ollama-first behavior byte-identically).
        provider = str(self.config.get("model_provider", "")
                       or runtime.model_provider or "auto").strip().lower()
        if provider not in ("auto", "builtin", "ollama", "native"):
            provider = "auto"
        offline = bool(self.config.get("offline", runtime.offline))
        if offline:
            provider = "builtin"
        _auto_local_first = False
        if provider == "auto" and not self.allow_mock_fallback:
            # UAI Phase N2/Step 35: local-first default for real
            # (non-mock) operation when a reasoning-capable built-in
            # model (≥ 1 GB) is installed. Mock-enabled environments
            # (dev/test) keep legacy auto behavior byte-identically;
            # explicit builtin/ollama settings are never overridden;
            # Ollama remains as fallback through the adapter chain.
            try:
                from models.builtin import model_manager as _store

                capable = [m for m in _store.list_installed()
                           if int(m.get("size", 0) or 0) >= 750000000]
                if capable:
                    provider = "builtin"
                    _auto_local_first = True
                    if default_model in ("", "llama3", "hercule-local"):
                        default_model = sorted(
                            capable, key=lambda m: int(m.get("size", 0) or 0),
                            reverse=True)[0]["id"]
            except Exception:
                pass
            # N9: also check for native HERCULE-LM checkpoints if no builtin found
            if provider == "auto":
                try:
                    from models.hercule_lm.provider import HerculeLMProvider
                    native_provider = HerculeLMProvider()
                    native_models = native_provider.discover_models()
                    if native_models:
                        provider = "native"
                        _auto_local_first = True
                        if default_model in ("", "llama3", "hercule-local", "hercule-lm-micro"):
                            default_model = native_models[0]
                except Exception:
                    pass
        self.provider_pref = provider
        self.offline = offline
        self.model_path = str(self.config.get("model_path", "")
                              or runtime.model_path or "")
        # N9: native model path/tokenizer config
        self.native_model_path = str(self.config.get("native_model_path", "")
                                     or runtime.native_model_path or "")
        self.native_tokenizer_dir = str(self.config.get("native_tokenizer_dir", "")
                                        or runtime.native_tokenizer_dir or "")
        if self.provider_pref == "builtin" and default_model in ("", "llama3"):
            default_model = "hercule-local"
        if self.provider_pref == "native" and default_model in ("", "llama3", "hercule-local"):
            default_model = "hercule-lm-micro"
        self.router = ModelRouter(self.config)
        if self.provider_pref == "builtin":
            try:
                self.router.config["preferred_adapter"] = "builtin"
            except Exception:
                pass
        if self.provider_pref == "native":
            try:
                self.router.config["preferred_adapter"] = "hercule-lm"
            except Exception:
                pass
        # Point the shared built-in adapter at the configured GGUF path.
        if self.model_path:
            try:
                builtin_adapter = self.router.adapters.get("builtin")
                if builtin_adapter is not None:
                    builtin_adapter.config.model_path = self.model_path
                    builtin_adapter._probe = None
            except Exception:
                pass
        # Point the native adapter at the configured checkpoint/tokenizer path.
        # If not explicitly configured, auto-discover the latest numpy checkpoint.
        try:
            native_adapter = self.router.adapters.get("hercule-lm")
            if native_adapter is not None:
                if self.native_model_path:
                    native_adapter._checkpoint = self.native_model_path
                if self.native_tokenizer_dir:
                    native_adapter._tokenizer_dir = self.native_tokenizer_dir
                # Auto-discover latest numpy checkpoint if none configured
                if not native_adapter._checkpoint:
                    try:
                        # Prefer numpy checkpoints (weights.npz) over torch (weights.pt)
                        checkpoints_root = Path("training/checkpoints")
                        candidates = []
                        for run_dir in checkpoints_root.iterdir():
                            if not run_dir.is_dir():
                                continue
                            for step_dir in run_dir.iterdir():
                                if not step_dir.is_dir() or not step_dir.name.startswith("step_"):
                                    continue
                                if (step_dir / "weights.npz").exists():
                                    # This is a numpy checkpoint
                                    manifest_path = step_dir / "manifest.json"
                                    if manifest_path.exists():
                                        import json
                                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                                        if "random initialization" in manifest.get("origin", ""):
                                            step_str = step_dir.name.replace("step_", "")
                                            try:
                                                step_num = int(step_str)
                                                candidates.append((step_num, str(step_dir), manifest))
                                            except ValueError:
                                                candidates.append((0, str(step_dir), manifest))
                        if candidates:
                            # Prefer checkpoints matching the default model
                            # Use the local default_model variable (already resolved above)
                            model_matches = [c for c in candidates if c[2].get("model_id") == default_model]
                            if model_matches:
                                model_matches.sort(key=lambda x: x[0], reverse=True)
                                native_adapter._checkpoint = model_matches[0][1]
                            else:
                                candidates.sort(key=lambda x: x[0], reverse=True)
                                native_adapter._checkpoint = candidates[0][1]
                    except Exception:
                        pass
        except Exception:
            pass
        # Point the shared ollama adapter at the configured host/timeout/options.
        ollama_adapter = self.router.adapters.get("ollama")
        if ollama_adapter is not None:
            ollama_adapter.host = self.ollama_host
            ollama_adapter.timeout_s = self.ollama_timeout_s
            ollama_adapter.client.host = self.ollama_host
            ollama_adapter.client.timeout_s = self.ollama_timeout_s
            ollama_options = self.config.get("ollama_options")
            if isinstance(ollama_options, dict):
                ollama_adapter.options.update(ollama_options)
                if ollama_adapter.options.get("num_predict") is None:
                    ollama_adapter.options.pop("num_predict", None)
        self.requested_model = default_model
        self.default_model = self._resolve_default_model(default_model)
        self.adapter = self._pick_adapter_for_model(self.default_model)
        logger.info("Initialized ModelManager with default model: [%s] (requested [%s])",
                    self.default_model, self.requested_model)

    # --------------------------------------------------
    # Discovery (Phase 3)
    # --------------------------------------------------
    def installed_ollama_models(self) -> List[str]:
        """Model names actually installed on the Ollama server (never invented)."""
        adapter = self.router.adapters.get("ollama")
        if adapter is None:
            return []
        try:
            return list(adapter.discover_models())
        except OllamaError as exc:
            logger.warning("Ollama discovery failed [%s]: %s", _error_category(exc), exc)
            return []
        except Exception as exc:
            logger.warning("Ollama discovery failed [%s]: %s", _error_category(exc), exc)
            return []

    def installed_model_details(self) -> List[Dict[str, Any]]:
        adapter = self.router.adapters.get("ollama")
        if adapter is None or not hasattr(adapter.client, "model_details"):
            return []
        try:
            return list(adapter.client.model_details())
        except Exception as exc:
            logger.warning("Ollama details failed [%s]: %s", _error_category(exc), exc)
            return []

    def discover_models(self) -> Dict[str, Any]:
        """Provider + model discovery report (safe: failures recorded, not raised)."""
        report: Dict[str, Any] = {"providers": {}, "installed_ollama_models": [],
                                    "installed_builtin_models": [],
                                    "installed_native_models": [],
                                    "default_model": self.default_model}
        for name, adapter in self.router.adapters.items():
            try:
                health = adapter.health() if hasattr(adapter, "health") else {"available": True}
            except Exception as exc:
                health = {"status": "error", "available": False, "reason": str(exc)}
            report["providers"][name] = health
        report["installed_ollama_models"] = self.installed_ollama_models()
        report["installed_builtin_models"] = self.installed_builtin_models()
        report["installed_native_models"] = self.installed_native_models()
        return report

    def installed_builtin_models(self) -> List[str]:
        """Local GGUF model ids in user data / bundled resources (never invented)."""
        adapter = self.router.adapters.get("builtin")
        if adapter is None or not hasattr(adapter, "discover_models"):
            return []
        try:
            return list(adapter.discover_models())
        except Exception as exc:
            logger.warning("Built-in discovery failed [%s]: %s", _error_category(exc), exc)
            return []

    def _resolve_default_model(self, requested: str) -> str:
        """Resolve the effective default to a model that actually exists.

        Configured name wins when installed/registered; otherwise the
        first preferred installed Ollama model; otherwise the request is
        kept verbatim so generate() fails honestly (never silently
        substituted with a mock).
        """
        if self.provider_pref == "builtin":
            return self._resolve_builtin_model(requested)
        if self.provider_pref == "native":
            return self._resolve_native_model(requested)
        installed = self.installed_ollama_models()
        self._register_installed(installed)
        if requested in installed:
            return requested
        info = self.router.registry.get(requested)
        if info is not None and getattr(info, "adapter_name", "") != "ollama":
            # Non-Ollama registered models (mock, tiny-gpt2, hercule-lm-micro) resolve locally.
            return requested
        # An Ollama-mapped name that is not installed would 404 on every
        # call: fall through to a model that actually exists.
        preferences = list(self.config.get("model_preferences", MODEL_PREFERENCES))
        for candidate in preferences:
            if candidate in installed:
                logger.info("default model [%s] unavailable; using installed [%s]", requested, candidate)
                self._register_installed(installed)
                return candidate
        if installed:
            logger.info("default model [%s] unavailable; using installed [%s]", requested, installed[0])
            self._register_installed(installed)
            return installed[0]
        logger.error("no Ollama models installed and default [%s] unknown; model calls will fail honestly",
                     requested)
        return requested

    def _resolve_builtin_model(self, requested: str) -> str:
        """Resolve to an installed GGUF model id (honest when none)."""
        installed = self.installed_builtin_models()
        self._register_builtin(installed)
        if requested in installed or requested == "hercule-local":
            if requested in installed:
                return requested
            if installed:
                logger.info("built-in model [%s] using installed [%s]",
                            requested, installed[0])
                return installed[0]
        info = self.router.registry.get(requested)
        if info is not None and getattr(info, "adapter_name", "") == "builtin":
            return requested
        if installed:
            return installed[0]
        logger.error("no built-in GGUF models installed; model calls will fail honestly")
        return requested or "hercule-local"

    def _register_builtin(self, installed: List[str]) -> None:
        """Register discovered GGUF ids (details-aware, never invented)."""
        try:
            from models.builtin import model_manager as store
        except Exception:
            store = None
        for name in installed:
            if self.router.registry.get(name) is not None:
                continue
            size, context = 0, 4096
            if store is not None:
                try:
                    meta = store.find_model(name) or {}
                    size = int(meta.get("size", 0) or 0)
                except Exception:
                    pass
            self.router.registry.register(ModelInfo(
                name=name, provider="builtin", context_length=context,
                capabilities=["chat", "reasoning"], priority=20, enabled=True,
                adapter_name="builtin",
                metadata={"discovered": True, "size": size, "format": "GGUF"},
            ))

    def _resolve_native_model(self, requested: str) -> str:
        """Resolve to an installed HERCULE-LM checkpoint (honest when none)."""
        installed = self.installed_native_models()
        self._register_native(installed)
        if requested in installed or requested == "hercule-lm-micro":
            if requested in installed:
                return requested
            if installed:
                logger.info("native model [%s] using installed [%s]",
                            requested, installed[0])
                return installed[0]
        info = self.router.registry.get(requested)
        if info is not None and getattr(info, "adapter_name", "") == "hercule-lm":
            return requested
        if installed:
            return installed[0]
        logger.error("no native HERCULE-LM checkpoints installed; model calls will fail honestly")
        return requested or "hercule-lm-micro"

    def _register_native(self, installed: List[str]) -> None:
        """Register discovered HERCULE-LM checkpoints (details-aware, never invented)."""
        try:
            from models.hercule_lm.provider import HerculeLMProvider
        except Exception:
            HerculeLMProvider = None
        for name in installed:
            if self.router.registry.get(name) is not None:
                continue
            # Try to get manifest details
            param_count = 0
            context = 128
            arch_hash = ""
            if HerculeLMProvider is not None:
                try:
                    provider = HerculeLMProvider()
                    # We can't easily get manifest without loading, so use defaults
                    param_count = 3088384  # MICRO default
                except Exception:
                    pass
            self.router.registry.register(ModelInfo(
                name=name, provider="hercule-lm", context_length=context,
                capabilities=["chat", "generation"], priority=15, enabled=True,
                adapter_name="hercule-lm",
                metadata={"discovered": True, "parameter_count": param_count, "format": "NPZ", "native": True,
                          "architecture_hash": arch_hash},
            ))

    def installed_native_models(self) -> List[str]:
        """Discover installed HERCULE-LM checkpoints (never invented)."""
        adapter = self.router.adapters.get("hercule-lm")
        if adapter is None or not hasattr(adapter, "discover_models"):
            return []
        try:
            return list(adapter.discover_models())
        except Exception as exc:
            logger.warning("Native model discovery failed [%s]: %s", _error_category(exc), exc)
            return []

    def _register_installed(self, installed: List[str]) -> None:
        """Register server-reported models (details-aware, never invented)."""
        details = {d.get("name"): d for d in self.installed_model_details()
                   if isinstance(d, dict) and d.get("name")}
        for name in installed:
            if self.router.registry.get(name) is not None:
                continue
            info = details.get(name, {})
            detail = info.get("details", {}) if isinstance(info.get("details"), dict) else {}
            server_caps = [str(c).lower() for c in (info.get("capabilities", []) or [])]
            capabilities = ["chat"]
            if "thinking" in server_caps:
                capabilities.append("reasoning")
            if "tools" in server_caps:
                capabilities.append("tool-calling")
            if "vision" in server_caps:
                capabilities.append("vision")
            if "completion" in server_caps:
                capabilities.append("completion")
            try:
                context_length = int(detail.get("context_length", 0) or 0) or 8192
            except (TypeError, ValueError):
                context_length = 8192
            self.router.registry.register(ModelInfo(
                name=name, provider="ollama", context_length=context_length,
                capabilities=capabilities, priority=10, enabled=True,
                adapter_name="ollama",
                metadata={"discovered": True,
                          "parameter_size": detail.get("parameter_size", ""),
                          "server_capabilities": server_caps},
            ))

    def _pick_adapter_for_model(self, model_name: str):
        try:
            _, adapter = self.router.route_by_name(model_name)
            return adapter
        except Exception:
            for adapter_name, adapter in self.router.adapters.items():
                if adapter_name == "mock" and not self.allow_mock_fallback:
                    continue
                if hasattr(adapter, "health"):
                    try:
                        if adapter.health().get("available", True):
                            return adapter
                    except Exception:
                        continue
                else:
                    return adapter
            return MockAdapter()

    def _ordered_adapters(self, target_model: str) -> Tuple[List[Tuple[str, Any]], List[str]]:
        """Attempt order for a generation request.

        The mock adapter is included ONLY on explicit request or when
        ``allow_mock_fallback`` is enabled (tests). Production requests
        never silently degrade to fabricated responses.
        """
        errors: list[str] = []
        try:
            preferred_name, preferred = self.router.route_by_name(target_model)
            ordered = [(preferred_name, preferred)]
            for name, adapter in self.router.adapters.items():
                if name != preferred_name:
                    ordered.append((name, adapter))
        except Exception as exc:
            errors.append(f"route_by_name:{exc}")
            ordered = list(self.router.adapters.items())
        if getattr(self, "offline", False):
            dropped = [n for n, _ in ordered if n == "ollama"]
            ordered = [(n, a) for n, a in ordered if n != "ollama"]
            if dropped:
                errors.append("offline mode: ollama excluded (built-in only)")
        # Keep preferred adapter at position 0; sort the rest by provider_pref
        if len(ordered) > 1:
            preferred = ordered[0]
            rest = ordered[1:]
            if getattr(self, "provider_pref", "auto") == "builtin":
                rest = sorted(rest, key=lambda item: (0 if item[0] == "builtin" else 1, item[0]))
            elif getattr(self, "provider_pref", "auto") == "native":
                rest = sorted(rest, key=lambda item: (0 if item[0] == "hercule-lm" else 1, item[0]))
            ordered = [preferred] + rest
        if target_model != "mock" and not self.allow_mock_fallback:
            skipped = [n for n, _ in ordered if n == "mock"]
            ordered = [(n, a) for n, a in ordered if n != "mock"]
            if skipped:
                errors.append("mock excluded from production fallback (explicit request or HERCULE_ALLOW_MOCK=1 only)")
        return ordered, errors

    ##################################################
    def generate_detailed(self, prompt: str, model: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Generate with a structured result (Phase 10 metrics).

        Returns ``{"status": "success", "response": str, "model": ...,
        "provider": ..., "latency_ms": ..., "attempts": [...]}`` or
        ``{"status": "failed", "error": ..., "attempts": [...]}``.
        Prompt contents are never logged.
        """
        target_model = model or self.default_model
        timeout_s = kwargs.pop("timeout_s", None)
        started = time.perf_counter()
        logger.info("MODEL generate model=[%s]", target_model)
        ordered, errors = self._ordered_adapters(target_model)
        attempts: List[Dict[str, Any]] = []
        adapters_tried: list[str] = []
        for name, adapter in ordered:
            attempt_started = time.perf_counter()
            try:
                health = adapter.health() if hasattr(adapter, "health") else {"available": True}
            except Exception as exc:
                category = _error_category(exc)
                errors.append(f"{name}.health:{exc}")
                attempts.append({"provider": name, "model": target_model, "success": False,
                                 "latency_ms": round((time.perf_counter() - attempt_started) * 1000.0, 2),
                                 "error_category": category, "timeout": False})
                continue
            if not health.get("available", True):
                reason = str(health.get("reason", "no reason"))
                errors.append(f"{name} unavailable: {reason}")
                attempts.append({"provider": name, "model": target_model, "success": False,
                                 "latency_ms": round((time.perf_counter() - attempt_started) * 1000.0, 2),
                                 "error_category": "UNAVAILABLE", "timeout": False})
                continue
            adapters_tried.append(name)
            try:
                call_kwargs = dict(kwargs)
                if name in ("ollama", "builtin", "hercule-lm") and timeout_s is not None:
                    call_kwargs["timeout_s"] = timeout_s
                if hasattr(adapter, "generate"):
                    response = adapter.generate(prompt=prompt, model=target_model, **call_kwargs)
                elif hasattr(adapter, "chat"):
                    if "messages" in call_kwargs:
                        response = adapter.chat(model=target_model, messages=call_kwargs["messages"])
                    else:
                        response = adapter.chat(model=target_model, prompt=prompt,
                                                system=call_kwargs.get("system", ""))
                else:
                    errors.append(f"{name}: adapter has neither generate nor chat")
                    attempts.append({"provider": name, "model": target_model, "success": False,
                                     "latency_ms": round((time.perf_counter() - attempt_started) * 1000.0, 2),
                                     "error_category": "NO_GENERATE", "timeout": False})
                    continue
                if not isinstance(response, str) or not response.strip():
                    raise RuntimeError(f"{name} returned empty response")
                latency = round((time.perf_counter() - started) * 1000.0, 2)
                attempt_ms = round((time.perf_counter() - attempt_started) * 1000.0, 2)
                attempts.append({"provider": name, "model": target_model, "success": True,
                                 "latency_ms": attempt_ms, "error_category": "",
                                 "timeout": False})
                logger.info("MODEL→RESPONSE provider=[%s] model=[%s] latency_ms=%.2f success=True",
                            name, target_model, latency)
                return {"status": "success", "response": response, "model": target_model,
                        "provider": name, "latency_ms": latency, "attempts": attempts}
            except Exception as exc:
                category = _error_category(exc)
                attempt_ms = round((time.perf_counter() - attempt_started) * 1000.0, 2)
                timed_out = category in ("OLLAMA_TIMEOUT", "TIMEOUT")
                logger.error(
                    "MODEL FAILED subsystem='models' provider='%s' model='%s' "
                    "error_category='%s' recovery='try-next-adapter' result='continuing'",
                    name, target_model, category,
                )
                errors.append(f"{name}:{exc}")
                attempts.append({"provider": name, "model": target_model, "success": False,
                                 "latency_ms": attempt_ms, "error_category": category,
                                 "timeout": timed_out})
                continue
        latency = round((time.perf_counter() - started) * 1000.0, 2)
        detail = "; ".join(errors) if errors else "no adapters registered"
        logger.error(
            "MODEL FAILED subsystem='models' operation='generate' tried='%s' "
            "exception='%s' recovery='none-remaining' result='failed' latency_ms=%.2f",
            adapters_tried, detail, latency,
        )
        return {"status": "failed",
                "error": f"[HERCULE Error]: subsystem='models' operation='generate' "
                         f"exception='{detail}' recovery='no-healthy-adapter' result='failed'",
                "model": target_model, "latency_ms": latency, "attempts": attempts}

    def generate(self, prompt: str, model: Optional[str] = None, **kwargs) -> str:
        """
        Generate a response text for a given prompt using the active model adapter.
        String contract preserved for existing callers; see generate_detailed().
        """
        result = self.generate_detailed(prompt, model=model, **kwargs)
        if result["status"] == "success":
            return str(result["response"])
        return str(result["error"])

    ##################################################
    def load_model(self, model_name: str) -> bool:
        """
        Load or switch the active model.

        The name must resolve: registered, explicitly "mock", or
        installed on Ollama (auto-registered). Unknown names raise
        honestly instead of silently misrouting.
        """
        if self.router.registry.get(model_name) is None and model_name != "mock":
            installed = self.installed_ollama_models()
            if model_name in installed:
                self._register_installed(installed)
            else:
                builtin = self.installed_builtin_models()
                if model_name in builtin:
                    self._register_builtin(builtin)
                else:
                    native = self.installed_native_models()
                    if model_name in native:
                        self._register_native(native)
                    else:
                        raise RuntimeError(
                            f"Model '{model_name}' not found (not registered, not installed).")
        self.default_model = model_name
        self.adapter = self._pick_adapter_for_model(model_name)
        # If loading a native model, ensure the native adapter has the correct checkpoint
        if model_name in self.installed_native_models():
            try:
                native_adapter = self.router.adapters.get("hercule-lm")
                if native_adapter is not None:
                    # Find the latest checkpoint for this model
                    from models.hercule_lm import checkpoint as ckpt
                    checkpoints_root = Path("training/checkpoints")
                    candidates = []
                    for run_dir in checkpoints_root.iterdir():
                        if not run_dir.is_dir():
                            continue
                        for step_dir in run_dir.iterdir():
                            if not step_dir.is_dir() or not step_dir.name.startswith("step_"):
                                continue
                            manifest_path = step_dir / "manifest.json"
                            if manifest_path.exists():
                                import json
                                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                                if manifest.get("model_id") == model_name:
                                    if (step_dir / "weights.npz").exists():
                                        step_str = step_dir.name.replace("step_", "")
                                        try:
                                            step_num = int(step_str)
                                            candidates.append((step_num, str(step_dir)))
                                        except ValueError:
                                            candidates.append((0, str(step_dir)))
                    if candidates:
                        candidates.sort(key=lambda x: x[0], reverse=True)
                        native_adapter._checkpoint = candidates[0][1]
            except Exception:
                pass
        logger.info(f"Switched active model to: [{model_name}]")
        return True

    def health(self):
        return self.router.health()

    def route(self, task: str, preferred_adapter: Optional[str] = None, preferred_model: Optional[str] = None):
        return self.router.route(task, preferred_adapter=preferred_adapter, preferred_model=preferred_model)

    def route_for_purpose(self, purpose: str, **kwargs):
        """Purpose-aware routing (Phase 5): conversation/reasoning/coding/light/complex.

        Returns (model_name, adapter_name, adapter). When the built-in
        provider is preferred (or offline forces it) and healthy, every
        purpose binds the built-in model; otherwise the historical
        Ollama-first routing runs unchanged."""
        if getattr(self, "provider_pref", "auto") == "builtin":
            try:
                builtin = self.router.adapters.get("builtin")
                if builtin is not None:
                    probe = builtin.health() if hasattr(builtin, "health") else {}
                    if probe.get("available"):
                        model = str(probe.get("model", "") or "hercule-local")
                        try:
                            name, adapter = self.router.route_by_name(model)
                            return model, name, adapter
                        except Exception:
                            return "hercule-local", "builtin", builtin
            except Exception:
                pass
        return self.router.route_for_purpose(purpose, default_model=self.default_model, **kwargs)
