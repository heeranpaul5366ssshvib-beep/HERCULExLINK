from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Advanced Model Router
Author: Heeran Paul
License: MIT
--------------------------------------------

Capability-, health-, latency-, resource- and history-aware routing
built *around* the existing ``ModelRouter`` (composition, no changes
to ``ModelRouter``/``ModelManager``):

capability match + availability + health + latency + resource fit
+ historical success -> transparent scores -> explainable decision

Fallback is an explicit chain (PRIMARY -> SECONDARY -> ... -> CLEAR
FAILURE). A total failure raises ``ModelRoutingFailure`` carrying the
decision — it is never reported as a success.

Ownership: MODELS.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from models.capabilities import ModelCapabilityRegistry, profile_from_info
from models.model_health import HealthState, ModelHealthMonitor
from models.routing_performance import RoutingMemory

_WEIGHTS = {
    "capability": 0.35,
    "availability": 0.20,
    "health": 0.15,
    "latency": 0.10,
    "resources": 0.10,
    "history": 0.10,
}

_TASK_CAPABILITY_HINTS = {
    "coding": "coding",
    "research": "reasoning",
    "engineering": "reasoning",
    "mathematics": "reasoning",
    "documents": "reasoning",
    "conversation": "reasoning",
    "general": "reasoning",
}

_HEALTH_WEIGHTS = {
    HealthState.AVAILABLE: 1.0,
    HealthState.READY: 1.0,
    HealthState.LOADING: 0.5,
    HealthState.DEGRADED: 0.4,
    HealthState.UNAVAILABLE: 0.0,
    HealthState.FAILED: 0.0,
}


class ModelRoutingFailure(RuntimeError):
    """Every adapter in the fallback chain failed. Carries ``decision``."""

    def __init__(self, message: str, decision: Optional["RoutingDecision"] = None):
        super().__init__(message)
        self.decision = decision


@dataclass
class CandidateScore:
    adapter_name: str
    model_name: str
    total: float
    factors: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "model_name": self.model_name,
            "total": round(self.total, 4),
            "factors": {k: round(v, 4) for k, v in self.factors.items()},
        }


@dataclass
class RoutingDecision:
    """Compact, explainable routing summary (no chain-of-thought)."""

    model: str
    adapter_name: str
    reason: str
    task_type: str
    scores: List[CandidateScore] = field(default_factory=list)
    fallback_chain: List[str] = field(default_factory=list)
    requirements: Dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "adapter_name": self.adapter_name,
            "reason": self.reason,
            "task_type": self.task_type,
            "scores": [s.as_dict() for s in self.scores],
            "fallback_chain": list(self.fallback_chain),
            "requirements": dict(self.requirements),
        }


def _classify_task_type(task: str) -> str:
    try:
        from models.classifier.classifier import TaskClassifier

        return str(TaskClassifier().classify(task or ""))
    except Exception:
        lowered = (task or "").lower()
        for keyword, label in (("code", "coding"), ("research", "research"), ("test", "general")):
            if keyword in lowered:
                return label
        return "general"


class AdvancedModelRouter:
    """Score-based router wrapping a ``ModelRouter`` instance."""

    def __init__(
        self,
        router: Any,
        capabilities: Optional[ModelCapabilityRegistry] = None,
        health_monitor: Optional[ModelHealthMonitor] = None,
        memory: Optional[RoutingMemory] = None,
        resource_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self.router = router
        self.capabilities = capabilities or ModelCapabilityRegistry()
        self.health_monitor = health_monitor or ModelHealthMonitor()
        self.memory = memory or RoutingMemory()
        self.resource_fn = resource_fn or (lambda: {"source": "unavailable"})
        self._ensure_profiles()

    # --------------------------------------------------
    def _ensure_profiles(self) -> None:
        registry = getattr(self.router, "registry", None)
        if registry is None:
            return
        for info in registry.all():
            if self.capabilities.get(info.name) is None:
                self.capabilities.register(profile_from_info(info))

    def _adapter_model_pairs(self) -> List[Tuple[str, str, Any]]:
        registry = getattr(self.router, "registry", None)
        adapters = dict(getattr(self.router, "adapters", {}) or {})
        pairs: List[Tuple[str, str, Any]] = []
        if registry is not None:
            for info in registry.all():
                if not getattr(info, "enabled", True):
                    continue
                adapter_name = getattr(info, "adapter_name", None)
                adapter = adapters.get(adapter_name) if adapter_name else None
                if adapter is not None:
                    pairs.append((adapter_name, info.name, adapter))
        if not pairs:  # registry-less router: route adapters directly
            for name, adapter in adapters.items():
                pairs.append((name, name, adapter))
        return pairs

    # --------------------------------------------------
    def route_with_scores(
        self,
        task: str,
        requirements: Optional[Dict[str, float]] = None,
        min_context: int = 0,
        max_latency_ms: float = 0.0,
        preferred_model: Optional[str] = None,
    ) -> Tuple[str, Any, RoutingDecision]:
        requirements = dict(requirements or {})
        task_type = _classify_task_type(task)
        if not requirements:
            hint = _TASK_CAPABILITY_HINTS.get(task_type, "reasoning")
            requirements = {hint: 0.3}
        resources = self.resource_fn() or {}

        scored: List[CandidateScore] = []
        live: Dict[str, Tuple[Any, str]] = {}
        for adapter_name, model_name, adapter in self._adapter_model_pairs():
            record = self.health_monitor.check(adapter_name, adapter)
            if not record.available or record.state == HealthState.FAILED:
                continue
            profile = self.capabilities.get(model_name)
            if profile is not None:
                if min_context and profile.context_length < min_context:
                    continue
                if max_latency_ms > 0 and profile.latency_ms > 0 and profile.latency_ms > max_latency_ms:
                    continue
                if any(profile.score_for(cap) < level for cap, level in requirements.items()):
                    continue  # incapable models fail closed, never silently picked
            factors = self._score_factors(
                model_name, task_type, requirements, record, resources, preferred_model
            )
            total = sum(_WEIGHTS[k] * factors.get(k, 0.0) for k in _WEIGHTS)
            scored.append(CandidateScore(adapter_name, model_name, total, factors))
            live[adapter_name] = (adapter, model_name)

        if not scored:
            empty = RoutingDecision(
                model="",
                adapter_name="",
                reason="clear failure: no healthy adapters, no silent fallback",
                task_type=task_type,
                requirements=requirements,
            )
            raise ModelRoutingFailure("Clear failure: no healthy model adapters available for task.", empty)
        scored.sort(key=lambda s: s.total, reverse=True)
        winner = scored[0]
        adapter, _ = live[winner.adapter_name]
        record = self.health_monitor.record(winner.adapter_name)
        if record is not None and record.state == HealthState.AVAILABLE:
            record.state = HealthState.READY
        decision = RoutingDecision(
            model=winner.model_name,
            adapter_name=winner.adapter_name,
            reason=self._explain(winner, task_type, requirements, resources),
            task_type=task_type,
            scores=scored,
            fallback_chain=[s.adapter_name for s in scored],
            requirements=requirements,
        )
        return winner.adapter_name, adapter, decision

    def _score_factors(
        self,
        model_name: str,
        task_type: str,
        requirements: Dict[str, float],
        record: Any,
        resources: Dict[str, Any],
        preferred_model: Optional[str],
    ) -> Dict[str, float]:
        profile = self.capabilities.get(model_name)
        if requirements and profile is not None:
            margins = [profile.score_for(cap) - level for cap, level in requirements.items()]
            capability = max(0.0, min(1.0, sum(margins) / len(margins) + 0.5)) if margins else 0.5
        else:
            capability = 0.5
        availability = 1.0  # unavailable adapters never reach scoring
        health = _HEALTH_WEIGHTS.get(getattr(record, "state", HealthState.LOADING), 0.0)
        latency_ms = 0.0
        if profile is not None and profile.latency_ms > 0:
            latency_ms = profile.latency_ms
        elif getattr(record, "latency_ms", 0.0):
            latency_ms = float(record.latency_ms)
        latency = 1.0 / (1.0 + latency_ms / 1000.0)
        resource_fit = 1.0
        if profile is not None:
            if resources.get("source") == "psutil" and profile.memory_mb > 0:
                available_mb = float(resources.get("ram_available_mb", 0.0) or 0.0)
                if available_mb > 0 and profile.memory_mb > available_mb:
                    resource_fit = 0.2
            if profile.memory_mb <= 0 and (profile.hardware or "cpu") != "cpu":
                resource_fit = min(resource_fit, 0.7)
        history = self.memory.success_rate(model_name, task_type)
        if preferred_model and model_name == preferred_model:
            capability = min(1.0, capability + 0.2)  # explicit user config wins ties
        return {
            "capability": capability,
            "availability": availability,
            "health": health,
            "latency": latency,
            "resources": resource_fit,
            "history": history,
        }

    @staticmethod
    def _explain(winner: CandidateScore, task_type: str, requirements: Dict[str, float], resources: Dict[str, Any]) -> str:
        reqs = ", ".join(f"{k}>={v}" for k, v in requirements.items()) or "general"
        base = f"best available capability match ({reqs}) for {task_type} task"
        if resources.get("source") == "psutil":
            base += " within measured resource budget"
        else:
            base += " within resource budget"
        ordered = sorted(winner.factors.items(), key=lambda kv: kv[1])
        if ordered and ordered[0][1] < 0.5:
            base += f"; weakest factor: {ordered[0][0]}"
        return base

    # --------------------------------------------------
    # Embedding routing: capability = EMBEDDING -> model id -> provider.
    # Execution belongs to EmbeddingManager; this only selects + explains.
    # --------------------------------------------------
    def route_embedding(
        self,
        task: str = "embed query",
        preferred_model: Optional[str] = None,
        min_dimension: int = 0,
    ) -> Tuple[str, RoutingDecision]:
        from models.capabilities import register_embedding_models

        register_embedding_models(self.capabilities)
        task_type = "embedding"
        scored: List[CandidateScore] = []
        for profile in self.capabilities.embedding_models():
            if min_dimension and (profile.dimension or 0) < min_dimension:
                continue
            factors = {
                "capability": max(0.0, min(1.0, profile.embeddings)),
                "availability": max(0.0, min(1.0, profile.availability)),
                "health": 1.0,
                "latency": 1.0 / (1.0 + (profile.latency_ms or 0.0) / 1000.0),
                "resources": 1.0,
                "history": self.memory.success_rate(profile.model_name, task_type),
            }
            if preferred_model and profile.model_name == preferred_model:
                factors["capability"] = min(1.0, factors["capability"] + 0.2)
            total = sum(_WEIGHTS[k] * factors[k] for k in _WEIGHTS)
            scored.append(CandidateScore(profile.model_name, profile.model_name, total, factors))
        if preferred_model and all(s.model_name != preferred_model for s in scored):
            raise ModelRoutingFailure(
                f"Clear failure: preferred embedding model '{preferred_model}' is not capable/registered.",
                RoutingDecision(model="", adapter_name="embeddings", reason="preferred embedding model incapable", task_type=task_type),
            )
        if not scored:
            raise ModelRoutingFailure(
                "Clear failure: no embedding-capable model registered.",
                RoutingDecision(model="", adapter_name="embeddings", reason="no embedding models", task_type=task_type),
            )
        scored.sort(key=lambda s: s.total, reverse=True)
        winner = scored[0]
        decision = RoutingDecision(
            model=winner.model_name,
            adapter_name=f"embeddings:{winner.model_name}",
            reason=f"best available embedding capability ({winner.model_name}, dim {self.capabilities.get(winner.model_name).dimension})",
            task_type=task_type,
            scores=scored,
            fallback_chain=[s.model_name for s in scored],
            requirements={"embeddings": 0.5},
        )
        return winner.model_name, decision

    def record_embedding_outcome(self, model_name: str, success: bool, latency_ms: float = 0.0) -> None:
        self.memory.record(model_name, "embedding", success, latency_ms)

    # --------------------------------------------------
    def generate_with_fallback(
        self,
        prompt: str,
        task: str = "",
        requirements: Optional[Dict[str, float]] = None,
        preferred_model: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> Tuple[str, RoutingDecision]:
        _, _, decision = self.route_with_scores(task, requirements, preferred_model=preferred_model)
        if task_type:
            decision.task_type = task_type
        else:
            task_type = decision.task_type
        errors: List[str] = []
        for candidate in decision.scores:
            started = time.perf_counter()
            adapter = dict(getattr(self.router, "adapters", {})).get(candidate.adapter_name)
            if adapter is None:
                errors.append(f"{candidate.adapter_name}: adapter missing")
                continue
            try:
                if hasattr(adapter, "generate"):
                    response = adapter.generate(prompt=prompt, model=candidate.model_name)
                elif hasattr(adapter, "chat"):
                    response = adapter.chat(model=candidate.model_name, prompt=prompt)
                else:
                    raise AttributeError(f"adapter '{candidate.adapter_name}' has no generate/chat")
                latency_ms = (time.perf_counter() - started) * 1000.0
                self.memory.record(candidate.model_name, task_type, True, latency_ms)
                return response, decision
            except Exception as exc:
                latency_ms = (time.perf_counter() - started) * 1000.0
                self.memory.record(candidate.model_name, task_type, False, latency_ms)
                errors.append(f"{candidate.adapter_name}: {exc}")
        failure = ModelRoutingFailure(
            "All model adapters failed: " + "; ".join(errors), decision
        )
        raise failure
