from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Runtime Monitor
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class RuntimeMonitor:
    """
    Monitors runtime execution,
    events and health.
    """

    def __init__(self):

        self.initialized = False

        self.events: List[Dict[str, Any]] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Runtime Monitor"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        self.events.clear()

        self.initialized = False

    # --------------------------------------------------

    def record(

        self,

        event: str,

        details: Dict[str, Any] | None = None,

    ):

        self.events.append(

            {

                "timestamp": datetime.now(timezone.utc).isoformat(),

                "event": event,

                "details": details or {},

            }

        )

    # --------------------------------------------------

    def latest(

        self,

        limit: int = 20,

    ):

        return self.events[-limit:]

    # --------------------------------------------------

    def clear(self):

        self.events.clear()

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "events": len(self.events),

        }