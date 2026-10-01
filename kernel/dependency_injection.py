from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Dependency Injection
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from kernel.registry import ServiceRegistry
from kernel.base_service import BaseService


class DependencyInjection:
    """
    Resolves services from the registry.
    """

    def __init__(self, registry: ServiceRegistry) -> None:
        self._registry = registry

    def resolve(self, name: str) -> BaseService:
        """
        Return the requested service.
        """

        return self._registry.get(name)

    def contains(self, name: str) -> bool:
        return self._registry.exists(name)