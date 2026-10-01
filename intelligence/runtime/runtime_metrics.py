from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Runtime Metrics
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from statistics import mean
from typing import Dict, List


logger = logging.getLogger(__name__)


class RuntimeMetrics:
    """
    Collects runtime performance
    statistics.
    """

    def __init__(self):

        self.initialized = False

        self.execution_times: List[float] = []

        self.total_requests = 0

        self.failed_requests = 0

        self.started = datetime.now(timezone.utc)

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Runtime Metrics"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        self.initialized = False

    # --------------------------------------------------

    def record(

        self,

        execution_time: float,

        success: bool = True,

    ):

        self.execution_times.append(

            execution_time

        )

        self.total_requests += 1

        if not success:

            self.failed_requests += 1

    # --------------------------------------------------

    def average_execution_time(self):

        if not self.execution_times:

            return 0.0

        return round(

            mean(self.execution_times),

            4,

        )

    # --------------------------------------------------

    def success_rate(self):

        if self.total_requests == 0:

            return 0.0

        successful = (

            self.total_requests -

            self.failed_requests

        )

        return round(

            successful /

            self.total_requests,

            3,

        )

    # --------------------------------------------------

    def report(self) -> Dict[str, object]:

        return {

            "started": self.started.isoformat(),

            "total_requests": self.total_requests,

            "failed_requests": self.failed_requests,

            "success_rate": self.success_rate(),

            "average_execution_time":

                self.average_execution_time(),

            "samples":

                len(self.execution_times),

        }

    # --------------------------------------------------

    def reset(self):

        self.execution_times.clear()

        self.total_requests = 0

        self.failed_requests = 0

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            **self.report(),

        }