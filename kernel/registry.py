from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Service Registry
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Dict

from kernel.base_service import BaseService
from kernel.exceptions import (
    ServiceAlreadyRegistered,
    ServiceNotFound,
)


class ServiceRegistry:
    """
    Stores all registered services.
    """

    def __init__(self) -> None:
        self._services: Dict[str, BaseService] = {}

    def register(self, service: BaseService) -> None:
        """
        Register a service.
        """

        if service.name in self._services:
            raise ServiceAlreadyRegistered(service.name)

        self._services[service.name] = service

    def unregister(self, name: str) -> None:
        """
        Remove a service.
        """

        if name not in self._services:
            raise ServiceNotFound(name)

        del self._services[name]

    def get(self, name: str) -> BaseService:
        """
        Get a service by name.
        """

        if name not in self._services:
            raise ServiceNotFound(name)

        return self._services[name]

    def exists(self, name: str) -> bool:
        return name in self._services

    def all(self) -> Dict[str, BaseService]:
        return self._services.copy()