from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Built-in Local Provider (v2)
Author: Heeran Paul
License: MIT
--------------------------------------------

Same generation contract as the Ollama adapter (health, chat,
generate, generate_detailed, discover_models) plus model lifecycle
(load_model/unload_model). Uses the managed llama.cpp runtime over
local GGUF weights. When no model is installed the provider reports
MODEL NOT INSTALLED honestly — it never fabricates text and never
falls back to the mock silently (the ModelManager owns fallback).
"""

import time
from typing import Any, Dict, List, Optional

from models.adapters.base_adapter import BaseAdapter
from models.builtin.config import (
    BuiltinConfig,
    default_threads,
    detect_gpu,
    load_builtin_config,
)


class BuiltinUnavailable(RuntimeError):
    pass


class BuiltinLocalProvider(BaseAdapter):
    """Local GGUF inference behind the standard adapter contract."""

    name = "builtin"

    def __init__(self, config: Optional[BuiltinConfig] = None,
                 runtime: Any = None, **kwargs: Any):
        self.config = config or load_builtin_config(overrides=kwargs or None)
        self._runtime = runtime
        self._model_id = ""
        self._probe: Optional[Dict[str, Any]] = None

    # --------------------------------------------------
    # Discovery / health (no generation, no downloads)
    # --------------------------------------------------
    def discover_models(self) -> List[str]:
        from models.builtin import model_manager as store

        return [m["id"] for m in store.list_installed()]

    def available(self) -> Dict[str, Any]:
        return self.health()

    def health(self) -> Dict[str, Any]:
        from models.builtin import model_manager as store

        if self._probe is not None and self._runtime is not None:
            return dict(self._probe)
        installed = self.discover_models()
        if not installed:
            self._probe = {"status": "unavailable", "available": False,
                           "reason": ("MODEL NOT INSTALLED: no GGUF weights in "
                                      + str(store.models_root() / "gguf"))}
            return dict(self._probe)
        # Prefer the actually-loaded/selected model id so health reports
        # what is running (UAI Phase N2: load_model resolved correctly
        # while health re-resolved via config and misreported it).
        wanted = self._model_id or self.config.model_path or self.config.model_id
        meta = store.find_model(wanted) or store.find_model(
            store.default_model_id())
        if meta is None:
            self._probe = {"status": "unavailable", "available": False,
                           "reason": f"model not installed: {wanted!r}",
                           "installed": installed}
            return dict(self._probe)
        info: Dict[str, Any] = {"status": "healthy", "available": True,
                                "model": meta["id"], "path": meta["path"],
                                "size": meta.get("size", 0),
                                "format": "GGUF",
                                "installed": installed}
        if self._runtime is not None and self._runtime.running:
            info.update({"loaded": True, "device": self._runtime.device,
                         "load_time_s": self._runtime.load_time_s,
                         "tokens_per_sec":
                             self._runtime.last_tokens_per_sec})
        else:
            info.update({"loaded": False, "device": "cpu"})
        self._probe = info
        return dict(self._probe)

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------
    def _runtime_or_raise(self) -> Any:
        from models.builtin.runtime import LlamaRuntime

        if self._runtime is None:
            threads = self.config.threads or default_threads()
            gpu = dict(detect_gpu())
            gpu_layers = self.config.gpu_layers
            if gpu_layers > 0 and not gpu.get("present"):
                gpu_layers = 0  # never claim GPU offload without a GPU
            self._runtime = LlamaRuntime(
                threads=threads, ctx_size=self.config.ctx_size,
                gpu_layers=gpu_layers, port=self.config.port,
                timeout_s=self.config.timeout_s)
        return self._runtime

    def load_model(self, model: str = "") -> Dict[str, Any]:
        from models.builtin import model_manager as store

        wanted = str(model or self.config.model_path
                     or self.config.model_id or "").strip()
        meta = store.find_model(wanted) if wanted else None
        if meta is None:
            meta = store.find_model(store.default_model_id())
        if meta is None:
            raise BuiltinUnavailable(
                "MODEL NOT INSTALLED: no GGUF weights available")
        runtime = self._runtime_or_raise()
        receipt = runtime.start(meta["path"])
        self._model_id = meta["id"]
        self._probe = None
        info = self.health()
        info["load_time_s"] = receipt.get("load_time_s", 0.0)
        return info

    def unload_model(self) -> Dict[str, Any]:
        if self._runtime is not None:
            self._runtime.stop()
        self._model_id = ""
        self._probe = None
        return {"unloaded": True}

    # --------------------------------------------------
    # Generation (same contract as the Ollama adapter)
    # --------------------------------------------------
    def _ensure_loaded(self) -> Any:
        runtime = self._runtime_or_raise()
        if not runtime.running:
            self.load_model()
        return runtime

    def chat(self, model: Optional[str] = None, prompt: str = "",
             system: str = "", messages: Optional[List[Dict[str, Any]]] = None,
             timeout_s: Optional[float] = None, **kwargs: Any) -> str:
        runtime = self._ensure_loaded()
        if messages:
            packed = [{"role": str(m.get("role", "user")),
                       "content": str(m.get("content", ""))}
                      for m in messages if isinstance(m, dict)]
        else:
            if not str(prompt or "").strip():
                raise BuiltinUnavailable("refusing empty prompt")
            packed = []
            if system:
                packed.append({"role": "system", "content": system})
            packed.append({"role": "user", "content": prompt})
        options = dict(kwargs.get("options", {}) or {})
        max_tokens = int(kwargs.get("max_tokens",
                                    options.get("n_predict",
                                                self.config.max_tokens)))
        temperature = float(kwargs.get("temperature",
                                       options.get("temperature",
                                                   self.config.temperature)))
        top_p = float(kwargs.get("top_p",
                                 options.get("top_p", self.config.top_p)))
        try:
            result = runtime.chat(packed, max_tokens=max_tokens,
                                  temperature=temperature, top_p=top_p,
                                  timeout_s=timeout_s or self.config.timeout_s)
        except TimeoutError:
            raise
        except BuiltinUnavailable:
            raise
        except Exception as exc:
            raise BuiltinUnavailable(f"built-in generation failed: {exc}")
        return str(result["text"])

    def generate(self, prompt: str, model: Optional[str] = None,
                 system: str = "", timeout_s: Optional[float] = None,
                 **kwargs: Any) -> str:
        return self.chat(model=model, prompt=prompt, system=system,
                         timeout_s=timeout_s, **kwargs)

    def generate_detailed(self, prompt: str, model: Optional[str] = None,
                          **kwargs: Any) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            text = self.generate(prompt, model=model, **kwargs)
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300],
                    "model": model or self._model_id,
                    "provider": "builtin",
                    "latency_ms": round((time.perf_counter() - started) * 1000.0, 2)}
        runtime = self._runtime
        return {"status": "success", "response": text,
                "model": model or self._model_id or self.config.model_id,
                "provider": "builtin",
                "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
                "tokens_per_sec": getattr(runtime, "last_tokens_per_sec", 0.0),
                "prompt_ms": getattr(runtime, "last_prompt_ms", 0.0),
                "gen_ms": getattr(runtime, "last_gen_ms", 0.0)}

    def embeddings(self, model: str, text: str):
        raise BuiltinUnavailable("built-in provider has no embedding model")
