"""
--------------------------------------------
HERCULE AI Operating System
Module: State Management
Author: Heeran Paul
License: MIT
--------------------------------------------
"""

from enum import Enum, auto


class SystemState(Enum):
    """
    Represents the global state of HERCULE.
    """

    CREATED = auto()
    INITIALIZING = auto()
    STARTING = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


class ServiceState(Enum):
    """
    Represents the lifecycle state of a service.
    """

    CREATED = auto()
    INITIALIZING = auto()
    READY = auto()
    RUNNING = auto()
    STOPPING = auto()
    STOPPED = auto()
    FAILED = auto()


class TaskState(Enum):
    """
    Represents the state of a task.
    """

    CREATED = auto()
    QUEUED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()