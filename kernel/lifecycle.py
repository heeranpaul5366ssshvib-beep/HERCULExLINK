from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Lifecycle Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from kernel.service_manager import ServiceManager
from kernel.state import SystemState


class LifecycleManager:
    """
    Controls startup and shutdown.
    """

    def __init__(self, services: ServiceManager) -> None:

        self._services = services
        self.state = SystemState.CREATED

    def initialize(self) -> None:

        self.state = SystemState.INITIALIZING
        self._services.initialize_all()

    def start(self) -> None:

        self.state = SystemState.STARTING

        self._services.start_all()

        self.state = SystemState.RUNNING

    def stop(self) -> None:

        self.state = SystemState.STOPPING

        self._services.stop_all()

        self.state = SystemState.STOPPED

    def restart(self) -> None:

        self.stop()

        self.initialize()

        self.start()