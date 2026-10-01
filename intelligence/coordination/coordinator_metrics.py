from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Coordinator Metrics
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class CoordinatorMetrics:
    """
    Collects operational metrics for the
    Intelligence Coordinator.

    Responsibilities

    • Execution statistics
    • Performance tracking
    • Component aggregation
    • Runtime reporting
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.started = datetime.now(timezone.utc)

        self.execution_times: List[float] = []

        self.total_requests = 0

        self.failed_requests = 0

        self.successful_requests = 0

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Coordinator Metrics"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Coordinator Metrics"
        )

        self.initialized = False

    # --------------------------------------------------

    def record_execution(

        self,

        duration: float,

        success: bool = True,

    ) -> None:

        self.execution_times.append(duration)

        self.total_requests += 1

        if success:

            self.successful_requests += 1

        else:

            self.failed_requests += 1

    # --------------------------------------------------

    def average_execution_time(self) -> float:

        if not self.execution_times:

            return 0.0

        return round(
            mean(self.execution_times),
            4,
        )

    # --------------------------------------------------

    def success_rate(self) -> float:

        if self.total_requests == 0:

            return 0.0

        return round(

            self.successful_requests

            / self.total_requests,

            3,

        )

    # --------------------------------------------------

    def component_statistics(self) -> Dict[str, Any]:
        """
        Collect statistics from registered
        coordinator components.
        """

        statistics: Dict[str, Any] = {}

        coordinator = getattr(
            self.kernel,
            "intelligence_coordinator",
            None,
        )

        if coordinator is None:

            return statistics

        components = {

            "runtime": getattr(
                coordinator,
                "runtime",
                None,
            ),

            "dispatcher": getattr(
                coordinator,
                "dispatcher",
                None,
            ),

            "registry": getattr(
                coordinator,
                "registry",
                None,
            ),

            "dependency_graph": getattr(
                coordinator,
                "dependency_graph",
                None,
            ),

            "execution_graph": getattr(
                coordinator,
                "execution_graph",
                None,
            ),

            "synchronization": getattr(
                coordinator,
                "synchronization",
                None,
            ),

            "health_monitor": getattr(
                coordinator,
                "health_monitor",
                None,
            ),
        }

        for name, component in components.items():

            if (
                component is not None
                and hasattr(component, "statistics")
            ):

                try:

                    statistics[name] = (
                        component.statistics()
                    )

                except Exception as exc:

                    logger.exception(

                        "Statistics failed for %s",

                        name,

                        exc_info=exc,

                    )

        return statistics

    # --------------------------------------------------

    def report(self) -> Dict[str, Any]:

        uptime = (

            datetime.now(timezone.utc)

            - self.started

        ).total_seconds()

        return {

            "timestamp":
                datetime.now(timezone.utc).isoformat(),

            "uptime_seconds":
                round(uptime, 3),

            "total_requests":
                self.total_requests,

            "successful_requests":
                self.successful_requests,

            "failed_requests":
                self.failed_requests,

            "success_rate":
                self.success_rate(),

            "average_execution_time":
                self.average_execution_time(),

            "components":
                self.component_statistics(),

        }

    # --------------------------------------------------

    def reset(self):

        self.execution_times.clear()

        self.total_requests = 0

        self.successful_requests = 0

        self.failed_requests = 0

        self.started = datetime.now(timezone.utc)

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized":
                self.initialized,

            **self.report(),

        }