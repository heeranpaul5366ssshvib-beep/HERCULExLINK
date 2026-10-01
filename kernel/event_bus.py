from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Event Bus
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from collections import defaultdict
from typing import Any, Callable


EventHandler = Callable[..., None]


class EventBus:
    """
    Publish/Subscribe event system.

    Services communicate through events instead
    of calling each other directly.
    """

    def __init__(self) -> None:

        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """
        Register an event handler.
        """

        if handler not in self._subscribers[event]:
            self._subscribers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """
        Remove an event handler.
        """

        if handler in self._subscribers[event]:
            self._subscribers[event].remove(handler)

    def publish(self, event: str, *args: Any, **kwargs: Any) -> None:
        """
        Notify every subscriber.
        """

        for handler in self._subscribers[event]:
            handler(*args, **kwargs)

    def clear(self) -> None:
        """
        Remove all subscribers.
        """

        self._subscribers.clear()