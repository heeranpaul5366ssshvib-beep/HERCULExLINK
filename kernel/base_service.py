from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Base Service
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abc import ABC, abstractmethod

from kernel.state import ServiceState


class BaseService(ABC):
    """
    Base class for every HERCULE service.
    """

    def __init__(self, name: str) -> None:

        self._name = name
        self._state = ServiceState.CREATED

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> ServiceState:
        return self._state

    def set_state(self, state: ServiceState) -> None:
        self._state = state

    @abstractmethod
    def initialize(self) -> None:
        """
        Prepare the service.
        """

    @abstractmethod
    def start(self) -> None:
        """
        Start the service.
        """

    @abstractmethod
    def stop(self) -> None:
        """
        Stop the service.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """
        Returns True if the service is healthy.
        """