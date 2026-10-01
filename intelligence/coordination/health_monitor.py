from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Health Monitor
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """
    Overall health states.
    """

    HEALTHY = "healthy"

    WARNING = "warning"

    CRITICAL = "critical"

    OFFLINE = "offline"


@dataclass
class HealthRecord:
    """
    Health snapshot for a module.
    """

    name: str

    status: HealthStatus

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    details: Dict[str, Any] = field(
        default_factory=dict
    )


class HealthMonitor:
    """
    Monitors the health of coordinator
    modules and the Intelligence Layer.

    Responsibilities

    • Health checks
    • Status aggregation
    • Event publication
    • Health history
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.records: Dict[str, HealthRecord] = {}

        self.history: List[HealthRecord] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Health Monitor"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Health Monitor"
        )

        self.records.clear()

        self.history.clear()

        self.initialized = False

    # --------------------------------------------------

    def update(

        self,

        module: str,

        status: HealthStatus,

        details: Optional[
            Dict[str, Any]
        ] = None,

    ) -> None:

        record = HealthRecord(

            name=module,

            status=status,

            details=details or {},

        )

        self.records[module] = record

        self.history.append(record)

        self._publish(
            record)

    # --------------------------------------------------

    def get(
        self,
        module: str,
    ) -> Optional[HealthRecord]:

        return self.records.get(module)

    # --------------------------------------------------

    def overall_status(
        self,
    ) -> HealthStatus:

        if not self.records:

            return HealthStatus.OFFLINE

        statuses = {

            record.status

            for record

            in self.records.values()

        }

        if HealthStatus.CRITICAL in statuses:

            return HealthStatus.CRITICAL

        if HealthStatus.WARNING in statuses:

            return HealthStatus.WARNING

        if HealthStatus.OFFLINE in statuses:

            return HealthStatus.OFFLINE

        return HealthStatus.HEALTHY

    # --------------------------------------------------

    def healthy_modules(self) -> List[str]:

        return [

            name

            for name, record

            in self.records.items()

            if record.status

            == HealthStatus.HEALTHY

        ]

    # --------------------------------------------------

    def unhealthy_modules(self) -> List[str]:

        return [

            name

            for name, record

            in self.records.items()

            if record.status

            != HealthStatus.HEALTHY

        ]

    # --------------------------------------------------

    def latest(
        self,
        limit: int = 20,
    ) -> List[HealthRecord]:

        return self.history[-limit:]

    # --------------------------------------------------

    def clear(self):

        self.records.clear()

        self.history.clear()

    # --------------------------------------------------

    def _publish(
        self,
        record: HealthRecord,
    ):

        if hasattr(
            self.kernel,
            "event_bus",
        ):

            self.kernel.event_bus.publish(

                "coordinator.health",

                {

                    "module":
                        record.name,

                    "status":
                        record.status.value,

                    "timestamp":
                        record.timestamp.isoformat(),

                },

            )

    # --------------------------------------------------

    def statistics(self):

        overall = self.overall_status()

        return {

            "initialized":
                self.initialized,

            "overall_status":
                overall.value,

            "tracked_modules":
                len(self.records),

            "healthy_modules":
                len(
                    self.healthy_modules()
                ),

            "unhealthy_modules":
                len(
                    self.unhealthy_modules()
                ),

            "history_entries":
                len(self.history),

        }