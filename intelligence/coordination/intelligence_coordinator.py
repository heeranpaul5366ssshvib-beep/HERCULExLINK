from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intelligence Coordinator
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from intelligence.runtime.intelligence_runtime import (
    IntelligenceRuntime,
)


logger = logging.getLogger(__name__)


class IntelligenceCoordinator:
    """
    Central coordinator of the
    Intelligence Layer.

    Responsibilities

    • Receive requests
    • Coordinate runtime execution
    • Manage execution context
    • Route requests
    • Publish events
    • Return unified responses
    """

    def __init__(
        self,
        kernel,
        manager,
    ):

        self.kernel = kernel

        self.manager = manager

        self.runtime = IntelligenceRuntime(
            kernel,
            manager,
        )

        self.initialized = False

        self.executions = 0

        self.started = None

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Intelligence Coordinator"
        )

        self.runtime.initialize()

        self.started = datetime.now(timezone.utc)

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Intelligence Coordinator"
        )

        self.runtime.shutdown()

        self.initialized = False

    # --------------------------------------------------

    def execute(
        self,
        request: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.executions += 1

        logger.info(
            "Executing intelligence request"
        )

        result = self.runtime.process(
            request
        )

        self.publish(
            "intelligence.completed",
            result,
        )

        return result

    # --------------------------------------------------

    def publish(
        self,
        event: str,
        payload: Optional[Any] = None,
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

    def health(self):

        return {

            "initialized":
                self.initialized,

            "runtime":
                self.runtime.initialized,

            "executions":
                self.executions,

        }

    # --------------------------------------------------

    def statistics(self):

        uptime = None

        if self.started:

            uptime = (

                datetime.now(timezone.utc)

                - self.started

            ).total_seconds()

        return {

            "initialized":
                self.initialized,

            "executions":
                self.executions,

            "uptime_seconds":
                uptime,

        }