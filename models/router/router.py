from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Model Router
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from models.registry.registry import ModelRegistry


class ModelRouter:
    """
    Selects the best model for a task.
    """

    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    def route(self, task: str):
        """
        Return the best model for the given task.
        """

        candidates = self.registry.by_capability(task)

        if not candidates:
            candidates = self.registry.enabled()

        if not candidates:
            raise RuntimeError("No models available.")

        candidates.sort(key=lambda m: m.priority)

        return candidates[0]

    def route_by_name(self, model_name: str):

        model = self.registry.get(model_name)

        if model is None:
            raise RuntimeError(f"Model '{model_name}' not found.")

        if not model.enabled:
            raise RuntimeError(f"Model '{model_name}' is disabled.")

        return model