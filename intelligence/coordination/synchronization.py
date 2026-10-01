from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Synchronization Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class SynchronizationBarrier:
    """
    Synchronization point for one
    execution layer.
    """

    name: str

    expected: int

    completed: int = 0

    created: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    released: bool = False


class SynchronizationManager:
    """
    Coordinates concurrent execution
    between intelligence modules.

    Responsibilities

    • Execution barriers
    • Layer synchronization
    • Completion tracking
    • Timeout support
    • Event notifications
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.lock = threading.RLock()

        self.barriers: Dict[
            str,
            SynchronizationBarrier
        ] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Synchronization Manager"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Synchronization Manager"
        )

        self.barriers.clear()

        self.initialized = False

    # --------------------------------------------------

    def create_barrier(

        self,

        name: str,

        expected: int,

    ):

        with self.lock:

            self.barriers[name] = (

                SynchronizationBarrier(

                    name=name,

                    expected=max(1, expected),

                )

            )

    # --------------------------------------------------

    def arrive(

        self,

        name: str,

    ) -> bool:

        with self.lock:

            barrier = self.barriers.get(name)

            if barrier is None:

                return False

            barrier.completed += 1

            if (

                barrier.completed

                >= barrier.expected

            ):

                barrier.released = True

                self._publish(

                    "sync.barrier.released",

                    {

                        "barrier": name,

                    },

                )

                return True

            return False

    # --------------------------------------------------

    def wait(

        self,

        name: str,

        timeout: Optional[float] = None,

    ) -> bool:

        start = datetime.now(timezone.utc)

        while True:

            with self.lock:

                barrier = self.barriers.get(

                    name

                )

                if (

                    barrier

                    and barrier.released

                ):

                    return True

            if timeout is not None:

                elapsed = (

                    datetime.now(timezone.utc)

                    - start

                ).total_seconds()

                if elapsed >= timeout:

                    return False

            threading.Event().wait(0.01)

    # --------------------------------------------------

    def release(

        self,

        name: str,

    ):

        with self.lock:

            barrier = self.barriers.get(name)

            if barrier:

                barrier.released = True

                self._publish(

                    "sync.barrier.manual_release",

                    {

                        "barrier": name,

                    },

                )

    # --------------------------------------------------

    def remove(

        self,

        name: str,

    ):

        with self.lock:

            self.barriers.pop(name, None)

    # --------------------------------------------------

    def clear(self):

        with self.lock:

            self.barriers.clear()

    # --------------------------------------------------

    def _publish(

        self,

        event: str,

        payload: dict,

    ):

        if hasattr(

            self.kernel,

            "event_bus",

        ):

            self.kernel.event_bus.publish(

                event,

                payload,

            )

    # --------------------------------------------------

    def statistics(self):

        released = sum(

            barrier.released

            for barrier

            in self.barriers.values()

        )

        return {

            "initialized":
                self.initialized,

            "barriers":
                len(self.barriers),

            "released":
                released,

            "waiting":
                len(self.barriers)

                - released,

        }