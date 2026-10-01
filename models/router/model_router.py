from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models.adapters.mock_adapter import MockAdapter
from models.registry.registry import ModelInfo, ModelRegistry

logger = logging.getLogger("HERCULE.Models.ModelRouter")


_ADAPTER_FACTORIES = {
    "mock": lambda: MockAdapter(),
    "ollama": lambda: __import__("models.adapters.ollama_adapter", fromlist=["OllamaAdapter"]).OllamaAdapter(),
    "transformers": lambda: __import__("models.adapters.transformers_adapter", fromlist=["TransformersAdapter"]).TransformersAdapter(),
    "builtin": lambda: __import__("models.adapters.builtin_adapter", fromlist=["BuiltinAdapter"]).BuiltinAdapter(),
    "hercule-lm": lambda: __import__("models.hercule_lm.provider", fromlist=["HerculeLMProvider"]).HerculeLMProvider(),
}


class ModelRouter:
    """Select the best available adapter/model for a task.

    Strategy:
    - Prefer explicit config selection when provided.
    - Validate adapter availability and health.
    - Auto-fallback to the next healthy adapter.
    - Route heavy tasks to high-quality local models; light tasks to mock or fast adapters.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = {
            "preferred_adapter": "ollama",
            "preferred_model": "llama3",
            "fallback_adapters": ["mock", "transformers", "ollama"],
            "heavy_task_capability": "reasoning",
            "light_task_capability": "testing",
            "adapter_health_check": True,
        }
        if config:
            self.config.update(config)
        self.registry = ModelRegistry()
        self._adapter_factories: Dict[str, Any] = dict(_ADAPTER_FACTORIES)
        self._adapters: Dict[str, Any] = {}
        self._register_default_models()

    def _get_adapter(self, name: str) -> Optional[Any]:
        """Lazily get or create adapter."""
        if name in self._adapters:
            return self._adapters[name]
        factory = self._adapter_factories.get(name)
        if factory is None:
            return None
        try:
            adapter = factory()
            self._adapters[name] = adapter
            return adapter
        except Exception as exc:
            logger.info("Adapter %s unavailable: %s", name, exc)
            return None

    @property
    def adapters(self) -> Dict[str, Any]:
        """Get initialized adapters. Only initializes adapters in fallback chain on demand."""
        # Return already initialized adapters without triggering new initialization
        return self._adapters.copy()

    def _register_default_models(self):
        for name, provider in [("mock", "mock"), ("llama3", "ollama"), ("tiny-gpt2", "transformers"),
                               ("hercule-local", "builtin"), ("hercule-lm-micro", "hercule-lm")]:
            self.registry.register(
                ModelInfo(
                    name=name,
                    provider=provider,
                    context_length=4096 if provider in ("ollama", "builtin") else 128 if provider == "hercule-lm" else 1024,
                    capabilities=["reasoning", "chat", "testing"] if provider != "hercule-lm" else ["chat", "generation"],
                    priority=10 if provider == "ollama" else 15 if provider == "hercule-lm" else 20 if provider == "builtin" else 50 if provider == "transformers" else 100,
                    enabled=True,
                    adapter_name=provider,
                    metadata={"default": name in ("llama3", "tiny-gpt2", "mock", "hercule-local"), "native": provider == "hercule-lm"},
                )
            )

    def _candidate_adapters(self, task: str, preferred: Optional[str] = None, preferred_model: Optional[str] = None) -> List[Tuple[str, Any]]:
        ordered: List[str] = []
        if preferred:
            ordered.append(preferred)
        if preferred_model:
            adapter_name = self._adapter_for_model(preferred_model)
            if adapter_name and adapter_name not in ordered:
                ordered.append(adapter_name)
        for name in self.config.get("fallback_adapters", []):
            if name not in ordered:
                ordered.append(name)

        candidates: List[Tuple[str, Any]] = []
        for adapter_name in ordered:
            adapter = self._get_adapter(adapter_name)
            if adapter is None:
                continue
            if self.config.get("adapter_health_check", True):
                health = adapter.health() if hasattr(adapter, "health") else {"status": "healthy", "available": True}
                if not health.get("available", True):
                    continue
            candidates.append((adapter_name, adapter))
        return candidates

    def _adapter_for_model(self, model_name: str) -> Optional[str]:
        if model_name in {"mock", "tiny-gpt2", "llama3", "hercule-local", "hercule-lm-micro"}:
            return {"mock": "mock", "tiny-gpt2": "transformers", "llama3": "ollama",
                    "hercule-local": "builtin", "hercule-lm-micro": "hercule-lm"}.get(model_name)
        return None

    def route(self, task: str, preferred_adapter: Optional[str] = None, preferred_model: Optional[str] = None):
        candidates = self._candidate_adapters(task, preferred_adapter, preferred_model)
        if not candidates:
            raise RuntimeError("No healthy model adapters available")
        heavy = self.config.get("heavy_task_capability", "reasoning")
        light = self.config.get("light_task_capability", "testing")
        task_lower = (task or "").lower()
        if any(token in task_lower for token in ["reason", "plan", "analyze", "design", "research", "code"]):
            return self._best_of(candidates, heavy)
        if any(token in task_lower for token in ["test", "smoke", "demo", "simple", "debug"]) or task_lower == "":
            return self._best_of(candidates, light)
        return candidates[0]

    def _best_of(self, candidates: Iterable[Tuple[str, Any]], capability: str):
        candidates = list(candidates)
        if not candidates:
            raise RuntimeError("No healthy model adapters available")
        preferred = str(self.config.get("preferred_adapter", "ollama"))
        order = {"ollama": 0, "builtin": 1, "transformers": 2, "hercule-lm": 3}
        if preferred == "builtin":
            order = {"builtin": 0, "ollama": 1, "transformers": 2, "hercule-lm": 3}
        elif preferred == "hercule-lm":
            order = {"hercule-lm": 0, "ollama": 1, "builtin": 2, "transformers": 3}
        ordered = sorted(candidates, key=lambda item: (order.get(item[0], 4), item[0]))
        if capability == "reasoning":
            for name, adapter in ordered:
                if name in {"ollama", "builtin", "transformers", "hercule-lm"}:
                    return (name, adapter)
        return ordered[0]

    def installed_ollama_models(self) -> List[str]:
        """Names installed on the Ollama server (never invented)."""
        adapter = self.adapters.get("ollama")
        if adapter is None or not hasattr(adapter, "discover_models"):
            return []
        try:
            return list(adapter.discover_models())
        except Exception as exc:
            logger.warning("Ollama model discovery failed: %s", exc)
            return []

    def installed_hercule_lm_models(self) -> List[str]:
        """Names of installed HERCULE-LM checkpoints (never invented)."""
        adapter = self.adapters.get("hercule-lm")
        if adapter is None or not hasattr(adapter, "discover_models"):
            return []
        try:
            return list(adapter.discover_models())
        except Exception as exc:
            logger.warning("HERCULE-LM model discovery failed: %s", exc)
            return []

    def route_for_purpose(self, purpose: str, default_model: str = "llama3",
                          preferred_model: Optional[str] = None) -> Tuple[str, str, Any]:
        """Purpose-aware routing over real adapters (Phase 5).

        Returns (model_name, adapter_name, adapter). Purposes:
        conversation/general → default model; reasoning →
        thinking-capable installed model; planning → default model
        (fast structured output), then thinking-capable, then largest
        installed; coding → code-capable installed model; light/small →
        smallest installed model; complex/strong → largest installed
        model. Only installed/registered models are ever selected;
        failures raise honestly.
        """
        purpose = str(purpose or "general").lower()
        if preferred_model:
            adapter_name, adapter = self.route_by_name(preferred_model)
            return preferred_model, adapter_name, adapter
        installed_all = self.installed_ollama_models()
        native_models = self.installed_hercule_lm_models()
        # Filter installed models to only those registered in the registry
        installed = [m for m in installed_all if self.registry.get(m) is not None]
        details: Dict[str, Dict[str, Any]] = {}
        adapter = self.adapters.get("ollama")
        if adapter is not None and hasattr(adapter, "client"):
            try:
                for entry in adapter.client.model_details():
                    if isinstance(entry, dict) and entry.get("name"):
                        details[str(entry["name"])] = entry
            except Exception:
                details = {}

        def server_caps(name: str) -> List[str]:
            info = details.get(name, {})
            caps = info.get("capabilities", []) if isinstance(info, dict) else []
            return [str(c).lower() for c in (caps or [])]

        def size_of(name: str) -> int:
            try:
                return int((details.get(name, {}) or {}).get("size", 0) or 0)
            except (TypeError, ValueError):
                return 0

        def _bind(model_name: str) -> Tuple[str, str, Any]:
            adapter_name, adapter = self.route_by_name(model_name)
            return model_name, adapter_name, adapter

        def _model_registered(name: str) -> bool:
            """Check if a model is registered in the registry."""
            return self.registry.get(name) is not None

        if purpose in ("reasoning", "reason"):
            thinkers = [m for m in installed if "thinking" in server_caps(m)]
            if thinkers:
                return _bind(sorted(thinkers, key=size_of, reverse=True)[0])
            # Fall back to native models for reasoning if no thinking-capable Ollama models
            if native_models:
                return _bind(native_models[0])
        if purpose in ("planning", "plan"):
            # Planning needs fast, instruction-following JSON output: prefer
            # the configured default model, then any thinking-capable model,
            # then the largest installed model. Never invent names.
            if _model_registered(default_model):
                return _bind(default_model)
            thinkers = [m for m in installed if "thinking" in server_caps(m)]
            if thinkers:
                return _bind(sorted(thinkers, key=size_of, reverse=True)[0])
            if native_models:
                return _bind(native_models[0])
            if installed:
                return _bind(sorted(installed, key=size_of, reverse=True)[0])
        elif purpose in ("coding", "code"):
            coders = [m for m in installed
                      if "coder" in m.lower() or "code" in " ".join(server_caps(m))]
            if coders:
                return _bind(sorted(coders, key=size_of, reverse=True)[0])
        elif purpose in ("light", "small", "fast"):
            if installed:
                return _bind(sorted(installed, key=size_of)[0])
            if native_models:
                return _bind(native_models[0])
        elif purpose in ("complex", "strong", "best"):
            if installed:
                return _bind(sorted(installed, key=size_of, reverse=True)[0])
            if native_models:
                return _bind(native_models[0])
        # conversation/general/complex-fallback: configured default when usable.
        try:
            return _bind(default_model)
        except Exception:
            if installed:
                return _bind(sorted(installed, key=size_of, reverse=True)[0])
            if native_models:
                return _bind(native_models[0])
            raise RuntimeError(f"No model available for purpose '{purpose}'.")

    def route_by_name(self, model_name: str):
        candidate = self.registry.get(model_name)
        if candidate is None:
            raise RuntimeError(f"Model '{model_name}' not found.")
        adapter_name = candidate.adapter_name or self._adapter_for_model(model_name)
        if adapter_name is None:
            raise RuntimeError(f"No adapter registered for '{model_name}'.")
        adapter = self.adapters.get(adapter_name)
        if adapter is None:
            raise RuntimeError(f"Adapter '{adapter_name}' unavailable.")
        health = adapter.health() if hasattr(adapter, "health") else {"status": "healthy", "available": True}
        if not health.get("available", True):
            raise RuntimeError(f"Adapter '{adapter_name}' unhealthy: {health}")
        return adapter_name, adapter

    def select_adapter_for_task(self, task: str, preferred_adapter: Optional[str] = None, preferred_model: Optional[str] = None):
        route = self.route(task, preferred_adapter=preferred_adapter, preferred_model=preferred_model)
        return route[1]

    def health(self):
        status: Dict[str, Any] = {}
        # Always ensure mock adapter is initialized (always available)
        if "mock" in self._adapter_factories and "mock" not in self._adapters:
            self._get_adapter("mock")
        # Check health of already initialized adapters
        for name, adapter in self._adapters.items():
            health = adapter.health() if hasattr(adapter, "health") else {"status": "healthy", "available": True}
            status[name] = health
        return status
