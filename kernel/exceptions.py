"""
--------------------------------------------
HERCULE AI Operating System
Module: Kernel Exceptions
Author: Heeran Paul
License: MIT
--------------------------------------------
"""

class HerculeError(Exception):
    """Base exception for all HERCULE errors."""


class ServiceError(HerculeError):
    """Raised when a service fails."""


class ServiceAlreadyRegistered(ServiceError):
    """Raised when attempting to register an existing service."""


class ServiceNotFound(ServiceError):
    """Raised when a requested service does not exist."""


class ServiceInitializationError(ServiceError):
    """Raised when a service fails during initialization."""


class DependencyError(HerculeError):
    """Raised when dependency resolution fails."""


class EventError(HerculeError):
    """Raised when event processing fails."""


class ConfigurationError(HerculeError):
    """Raised when configuration is invalid."""