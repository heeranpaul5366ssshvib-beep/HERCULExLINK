from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Adapters
Author: Heeran Paul
License: MIT
--------------------------------------------

The ONLY paths by which evaluation tasks reach HERCULE. Adapters wrap
the real entry points — ``Brain.think`` for conversation-style tasks
and ``Brain.run_cycle`` for task-style tasks — and never reimplement
planning, capability resolution, policy or execution. The runtime
adapter tests the live pipeline; the hermetic adapter runs the same
pipeline in-process with the mock model backend; the scripted adapter
exists only for offline unit tests of the framework itself.
"""

import threading
from typing import Any, Dict, List, Optional


class EvalAdapter:
    """Interface the runner programs against."""

    name: str = "base"

    def think(self, prompt: str) -> str:
        raise NotImplementedError

    def classify(self, line: str) -> str:
        """HERCULE's deterministic request router (QUESTION/GOAL/MEMORY)."""
        raise NotImplementedError

    def run_goal(self, goal: str) -> Dict[str, Any]:
        raise NotImplementedError

    def default_model(self) -> str:
        return "UNKNOWN"

    def default_provider(self) -> str:
        return "UNKNOWN"

    def installed_models(self) -> List[str]:
        return []

    def set_model(self, model: str) -> None:
        raise NotImplementedError(f"adapter {self.name} cannot switch models")

    def close(self) -> None:  # pragma: no cover - interface default
        return None


class RuntimeEvalAdapter(EvalAdapter):
    """Live HERCULE runtime (initialized services) — the real pipeline."""

    name = "runtime"

    def __init__(self, services: Dict[str, Any], model: Optional[str] = None):
        self.services = services
        self.brain = services["brain"]
        self.models = services.get("models")
        self.memory = services.get("memory") or getattr(services.get("orchestrator"), "memory", None)
        self._boot_module: Any = None
        if model:
            self.set_model(model)

    def _boot(self):
        """Load the boot.py CLI module (same mechanism as the UI controller)."""
        if self._boot_module is None:
            import importlib.util
            import sys
            from pathlib import Path
            candidates = [Path(__file__).resolve().parent.parent.parent / "boot.py"]
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                candidates.insert(0, Path(meipass) / "boot.py")
            boot_path = next((p for p in candidates if p.exists()), candidates[-1])
            spec = importlib.util.spec_from_file_location("hercule_eval_boot", str(boot_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._boot_module = module
        return self._boot_module

    def classify(self, line: str) -> str:
        """Route one line through HERCULE's real deterministic classifier."""
        try:
            return str(self._boot().classify_request(str(line or "")))
        except Exception:
            return "UNKNOWN"

    def think(self, prompt: str) -> str:
        answer = self.brain.think(str(prompt or ""))
        return str(answer or "")

    def run_goal(self, goal: str) -> Dict[str, Any]:
        report = self.brain.run_cycle(str(goal or ""))
        if not isinstance(report, dict):
            return {"status": "error", "error": f"non-dict contract: {type(report).__name__}"}
        return report

    def default_model(self) -> str:
        try:
            return str(getattr(self.models, "default_model", "") or "UNKNOWN")
        except Exception:
            return "UNKNOWN"

    def default_provider(self) -> str:
        try:
            model = str(getattr(self.models, "default_model", "") or "")
            if model == "mock":
                return "mock"  # hermetic backend, never dress it up as ollama
            router = getattr(self.models, "router", None)
            adapters = getattr(router, "adapters", {}) or {}
            ollama = adapters.get("ollama")
            if ollama is not None:
                health = ollama.health() or {}
                return "ollama" if health.get("available") else "ollama (unavailable)"
        except Exception:
            pass
        return "UNKNOWN"

    def installed_models(self) -> List[str]:
        try:
            return list(self.models.installed_ollama_models() or [])
        except Exception:
            return []

    def set_model(self, model: str) -> None:
        """Rebind the default model (model comparison phase).

        Only models actually discovered/registered by ModelManager are
        accepted; anything else raises so the comparison never invents
        results for models that do not exist.
        """
        if self.models is None:
            raise RuntimeError("no ModelManager in services")
        installed = []
        try:
            installed = list(self.models.installed_ollama_models() or [])
        except Exception:
            installed = []
        registered = False
        try:
            registry = getattr(getattr(self.models, "router", None), "registry", None)
            registered = registry is not None and registry.get(model) is not None
        except Exception:
            registered = False
        if model not in installed and not registered:
            raise ValueError(f"model not installed/registered: {model}")
        try:
            self.models.default_model = model
        except Exception as exc:
            raise RuntimeError(f"cannot rebind default model: {exc}") from exc


class HermeticEvalAdapter(RuntimeEvalAdapter):
    """Same real pipeline, mock model backend, in-process.

    Used by tests and offline runs: initializes the canonical runtime
    with HERCULE_DEFAULT_MODEL=mock. No network, no Ollama required.

    UAI Phase M0: all mutable persistent state (tasks, memory,
    experience, skills, world) is redirected into an isolated
    directory — ``state_dir`` when given, otherwise a fresh temporary
    directory. Evaluation runs NEVER touch production stores.
    """

    name = "hermetic"

    _ISOLATION_KEYS = ("HERCULE_DEFAULT_MODEL", "HERCULE_ALLOW_MOCK",
                       "HERCULE_TASK_STORE", "HERCULE_MEMORY_DIR",
                       "HERCULE_EXPERIENCE_STORE", "HERCULE_SKILLS_STORE",
                       "HERCULE_WORLD_PATH", "HERCULE_TEST_GUARD",
                       "HERCULE_TEST_STATE_DIR")

    def __init__(self, model: Optional[str] = None, env: Optional[Dict[str, str]] = None,
                 state_dir: Optional[str] = None):
        import os
        import tempfile
        from pathlib import Path

        root = Path(state_dir) if state_dir else Path(
            tempfile.mkdtemp(prefix="hercule-eval-"))
        root.mkdir(parents=True, exist_ok=True)
        self.state_dir = str(root)
        isolated = {
            "HERCULE_DEFAULT_MODEL": model or "mock",
            "HERCULE_ALLOW_MOCK": "1",
            "HERCULE_TASK_STORE": ":memory:",
            "HERCULE_MEMORY_DIR": str(root / "memory"),
            "HERCULE_EXPERIENCE_STORE": str(root / "memory" / "experiences.json"),
            "HERCULE_SKILLS_STORE": str(root / "skills.json"),
            "HERCULE_WORLD_PATH": str(root / "world.json"),
            "HERCULE_TEST_GUARD": "1",
            "HERCULE_TEST_STATE_DIR": str(root),
        }
        if env:
            isolated.update({k: v for k, v in env.items() if v is not None})
        # UAI Phase M0: HERCULE resolves several store paths LAZILY from
        # the ambient environment at save time (experience, memory), so
        # the isolation environment is held for the adapter's whole
        # lifetime and restored only in close(). Adapters are serially
        # used; never share one across threads.
        self._saved_env = {k: os.environ.get(k) for k in self._ISOLATION_KEYS}
        os.environ.update(isolated)
        try:
            from runtime.initializer import RuntimeInitializer
            services = RuntimeInitializer().initialize()
        except Exception:
            self.close()
            raise
        super().__init__(services, model=None)
        self._owned_services = services

    def close(self) -> None:
        try:
            brain = getattr(self, "brain", None)
            if brain is not None:
                brain.stop()
        except Exception:
            pass
        finally:
            import os
            for key, value in (getattr(self, "_saved_env", {}) or {}).items():
                try:
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
                except Exception:
                    pass


class ScriptedEvalAdapter(EvalAdapter):
    """Canned responses for framework unit tests (never used in live runs)."""

    memory = None  # scripted adapter has no live memory

    name = "scripted"

    def __init__(self, think_rules: Optional[List[tuple]] = None,
                 goal_rules: Optional[List[tuple]] = None,
                 classify_rules: Optional[List[tuple]] = None,
                 default_goal: Optional[Dict[str, Any]] = None,
                 model: str = "scripted-mock"):
        # rules: list of (substring, response) — first match wins.
        self.think_rules = list(think_rules or [])
        self.goal_rules = list(goal_rules or [])
        self.classify_rules = list(classify_rules or [])
        self.default_goal = default_goal or {"status": "completed", "result": "ok",
                                             "verification": {"passed_steps": 1, "total_steps": 1},
                                             "replans": 0}
        self._model = model
        self.think_calls: List[str] = []
        self.goal_calls: List[str] = []

    def _match(self, rules, text):
        for substring, response in rules:
            if substring.lower() in text.lower():
                return response
        return None

    def think(self, prompt: str) -> str:
        self.think_calls.append(str(prompt or ""))
        return str(self._match(self.think_rules, str(prompt or "")) or "")

    def classify(self, line: str) -> str:
        return str(self._match(self.classify_rules, str(line or "")) or "")

    def run_goal(self, goal: str) -> Dict[str, Any]:
        self.goal_calls.append(str(goal or ""))
        response = self._match(self.goal_rules, str(goal or ""))
        return dict(response) if isinstance(response, dict) else dict(self.default_goal)

    def default_model(self) -> str:
        return self._model

    def default_provider(self) -> str:
        return "scripted"


def build_adapter(live: bool = True, model: Optional[str] = None,
                  services: Optional[Dict[str, Any]] = None) -> EvalAdapter:
    """Adapter factory: live runtime (existing or fresh) or hermetic."""
    if services is not None:
        return RuntimeEvalAdapter(services, model=model)
    if live:
        from runtime.initializer import RuntimeInitializer
        return RuntimeEvalAdapter(RuntimeInitializer().initialize(), model=model)
    return HermeticEvalAdapter(model=model)
