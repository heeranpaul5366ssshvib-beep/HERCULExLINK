from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Kernel
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from kernel.context import KernelContext
from kernel.dependency_injection import DependencyInjection
from kernel.event_bus import EventBus
from kernel.lifecycle import LifecycleManager
from kernel.scheduler import Scheduler
from kernel.service_manager import ServiceManager


class Kernel:
    """
    Central operating system of HERCULE.

    Every subsystem communicates through
    the Kernel.

    The Kernel owns:

    - Context
    - Service Manager
    - Event Bus
    - Scheduler
    - Dependency Injection
    - Lifecycle Manager
    """

    def __init__(self) -> None:

        self.context = KernelContext()

        self.service_manager = ServiceManager()

        self.event_bus = EventBus()

        self.scheduler = Scheduler()

        self.di = DependencyInjection(
            self.service_manager.registry
        )

        self.lifecycle = LifecycleManager(
            self.service_manager
        )

    # --------------------------------------------------

    def register_service(self, service):

        self.service_manager.register(service)

    # --------------------------------------------------

    def initialize(self):

        self.lifecycle.initialize()

    # --------------------------------------------------

    def start(self):

        self.lifecycle.start()

    # --------------------------------------------------

    def stop(self):

        self.scheduler.shutdown()

        self.lifecycle.stop()

    # --------------------------------------------------

    def publish(self, event, *args, **kwargs):

        self.event_bus.publish(
            event,
            *args,
            **kwargs,
        )

    # --------------------------------------------------

    def subscribe(self, event, handler):

        self.event_bus.subscribe(
            event,
            handler,
        )

    # --------------------------------------------------

    def get_service(self, name):

        return self.di.resolve(name)

    # --------------------------------------------------

    def health(self):

        return self.service_manager.health_check()