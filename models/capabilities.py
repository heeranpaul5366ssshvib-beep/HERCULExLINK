from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Model Capabilities
Author: Heeran Paul
License: MIT
--------------------------------------------

Explicit capability profiles per model. Model names alone are never
enough to determine capability: each profile carries graded scores
(0.0..1.0) for reasoning, coding, vision, embeddings, structured
output, tool calling and multimodal support, plus context length,
latency, memory, speed and hardware requirements.

Ownership: MODELS. Bridges the legacy ``ModelInfo`` registry entries
via ``profile_from_info``; the authoritative store going forward is
``ModelCapabilityRegistry``.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelCapability:
    """Measured/declared capability profile for one model."""

    model_name: str
    reasoning: float = 0.0
    coding: float = 0.0
    vision: float = 0.0
    embeddings: float = 0.0
    structured_output: float = 0.0
    tool_calling: float = 0.0
    multimodal: float = 0.0
    context_length: int = 1024
    latency_ms: float = 0.0  # measured p50 inference latency, 0 = unknown
    memory_mb: float = 0.0  # measured/declared footprint, 0 = unknown
    speed_tokens_per_s: float = 0.0
    hardware: str = "cpu"  # e.g. cpu, cuda:0, ollama-server
    availability: float = 1.0  # long-run availability 0..1
    dimension: int = 0  # embedding vector dimension, 0 = not an embedding model
    metadata: Dict[str, Any] = field(default_factory=dict)

    def score_for(self, capability: str) -> float:
        return float(getattr(self, capability, 0.0) or 0.0)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "reasoning": self.reasoning,
            "coding": self.coding,
            "vision": self.vision,
            "embeddings": self.embeddings,
            "structured_output": self.structured_output,
            "tool_calling": self.tool_calling,
            "multimodal": self.multimodal,
            "context_length": self.context_length,
            "latency_ms": self.latency_ms,
            "memory_mb": self.memory_mb,
            "speed_tokens_per_s": self.speed_tokens_per_s,
            "hardware": self.hardware,
            "availability": self.availability,
            "dimension": self.dimension,
            "metadata": dict(self.metadata),
        }


def profile_from_info(info: Any) -> ModelCapability:
    """Bridge a legacy ``ModelInfo`` entry to a capability profile.

    Legacy entries only carry string capability names, so declared
    capabilities map to 0.7 (present) and the mock provider to 0.3
    reasoning; real measurements overwrite these via ``update``.
    """
    name = str(getattr(info, "name", "unknown"))
    declared = list(getattr(info, "capabilities", []) or [])
    provider = str(getattr(info, "provider", ""))
    profile = ModelCapability(
        model_name=name,
        context_length=int(getattr(info, "context_length", 1024) or 1024),
        hardware="ollama-server" if provider == "ollama" else "cpu",
        metadata={"provider": provider, "adapter_name": getattr(info, "adapter_name", None)},
    )
    for cap in declared:
        key = str(cap).lower().replace("-", "_")
        if hasattr(profile, key):
            setattr(profile, key, 0.7)
    if provider == "mock":
        profile.reasoning = max(profile.reasoning, 0.3)
        profile.availability = 1.0
    return profile


class ModelCapabilityRegistry:
    """Authoritative capability store with requirement matching."""

    def __init__(self):
        self._profiles: Dict[str, ModelCapability] = {}

    def register(self, profile: ModelCapability) -> None:
        self._profiles[profile.model_name] = profile

    def get(self, model_name: str) -> Optional[ModelCapability]:
        return self._profiles.get(model_name)

    def all(self) -> List[ModelCapability]:
        return list(self._profiles.values())

    def update(self, model_name: str, **fields: Any) -> Optional[ModelCapability]:
        profile = self._profiles.get(model_name)
        if profile is None:
            return None
        for key, value in fields.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        return profile

    def matching(
        self,
        requirements: Dict[str, float],
        min_context: int = 0,
        max_latency_ms: float = 0.0,
    ) -> List[ModelCapability]:
        """Profiles meeting every graded requirement + constraints.

        Sorted by total requirement margin (best fit first).
        """
        candidates: List[tuple] = []
        for profile in self._profiles.values():
            if profile.context_length < min_context:
                continue
            if max_latency_ms > 0 and profile.latency_ms > 0 and profile.latency_ms > max_latency_ms:
                continue
            margins = [profile.score_for(cap) - level for cap, level in requirements.items()]
            if all(m >= 0 for m in margins):
                candidates.append((sum(margins), profile))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [profile for _, profile in candidates]

    def embedding_models(self, min_score: float = 0.5, include_test_only: bool = False) -> List[ModelCapability]:
        """Embedding-capable profiles, best embeddings score first."""
        models = [
            p
            for p in self._profiles.values()
            if p.embeddings >= min_score and (include_test_only or not p.metadata.get("test_only"))
        ]
        models.sort(key=lambda p: (p.embeddings, p.availability), reverse=True)
        return models


def register_embedding_models(registry: "ModelCapabilityRegistry") -> List[str]:
    """Declare the known embedding models (no weights loaded here).

    Model names are data, not hard-coded call sites: managers resolve
    them through the registry / router at runtime.
    """
    declared = [
        ModelCapability(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            embeddings=0.9,
            reasoning=0.0,
            context_length=256,
            memory_mb=90.0,
            speed_tokens_per_s=0.0,
            hardware="cpu",
            availability=0.9,
            dimension=384,
            metadata={"backend": "sentence-transformers", "normalized": True},
        ),
        ModelCapability(
            model_name="nomic-embed-text",
            embeddings=0.85,
            reasoning=0.0,
            context_length=8192,
            memory_mb=0.0,
            speed_tokens_per_s=0.0,
            hardware="ollama-server",
            availability=0.5,
            dimension=768,
            metadata={"backend": "ollama", "normalized": False},
        ),
        ModelCapability(
            model_name="hercule-hash-test-v1",
            embeddings=0.2,
            reasoning=0.0,
            context_length=1024,
            memory_mb=0.0,
            speed_tokens_per_s=0.0,
            hardware="cpu",
            availability=1.0,
            dimension=64,
            metadata={"backend": "hash", "normalized": True, "test_only": True},
        ),
    ]
    for profile in declared:
        if registry.get(profile.model_name) is None:
            registry.register(profile)
    return [p.model_name for p in declared]
