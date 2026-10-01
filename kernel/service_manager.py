from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Service Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from kernel.registry import ServiceRegistry
from kernel.base_service import BaseService
from kernel.state import ServiceState


class ServiceManager:
    """
    Controls the lifecycle of all services.
    """

    def __init__(self) -> None:
        self.registry = ServiceRegistry()

    def register(self, service: BaseService) -> None:
        """
        Register a new service.
        """

        self.registry.register(service)

    def initialize_all(self) -> None:
        """
        Initialize every registered service.
        """

        for service in self.registry.all().values():

            service.set_state(ServiceState.INITIALIZING)

            service.initialize()

            service.set_state(ServiceState.READY)

    def start_all(self) -> None:
        """
        Start every registered service.
        """

        for service in self.registry.all().values():

            service.start()

            service.set_state(ServiceState.RUNNING)

    def stop_all(self) -> None:
        """
        Stop every registered service.
        """

        for service in self.registry.all().values():

            service.stop()

            service.set_state(ServiceState.STOPPED)

    def health_check(self) -> dict[str, bool]:
        """
        Check health of every service.
        """

        result = {}

        for service in self.registry.all().values():

            result[service.name] = service.health_check()

        return result