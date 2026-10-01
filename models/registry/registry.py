from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Model Registry
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class ModelInfo:
    name: str
    provider: str
    context_length: int
    capabilities: List[str] = field(default_factory=list)
    priority: int = 100
    enabled: bool = True
    adapter_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelRegistry:

    def __init__(self):
        self._models: Dict[str, ModelInfo] = {}

    def register(self, model: ModelInfo):
        self._models[model.name] = model

    def unregister(self, name: str):
        self._models.pop(name, None)

    def get(self, name: str) -> Optional[ModelInfo]:
        return self._models.get(name)

    def exists(self, name: str) -> bool:
        return name in self._models

    def all(self):
        return list(self._models.values())

    def enabled(self):
        return [m for m in self._models.values() if m.enabled]

    def by_capability(self, capability: str):
        return [
            m
            for m in self.enabled()
            if capability in m.capabilities
        ]

    def by_provider(self, provider: str):
        return [m for m in self.enabled() if m.provider == provider]