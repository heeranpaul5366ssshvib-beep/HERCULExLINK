from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intelligence Metrics
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict


logger = logging.getLogger(__name__)


class IntelligenceMetrics:
    """
    Collects and aggregates metrics from every
    Intelligence Layer component.

    Responsibilities

    • System health
    • Performance monitoring
    • Accuracy tracking
    • Confidence reporting
    • Resource utilization
    • Historical statistics
    • Intelligence benchmarking
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.metrics: Dict[str, Dict[str, Any]] = {}

        self.last_updated: str | None = None

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Intelligence Metrics"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Intelligence Metrics"
        )

        self.metrics.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(self) -> Dict[str, Any]:

        report = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "modules": self.collect_modules(),

            "summary": self.summary(),

        }

        self.last_updated = report["timestamp"]

        return report

    # --------------------------------------------------

    def update_metric(

        self,

        module: str,

        values: Dict[str, Any],

    ):

        self.metrics[module] = values

        self.last_updated = datetime.now(timezone.utc).isoformat()

    # --------------------------------------------------

    def collect_modules(self) -> Dict[str, Dict[str, Any]]:

        modules = {}

        manager = getattr(

            self.kernel,

            "intelligence_manager",

            None,

        )

        if manager is None:

            return self.metrics.copy()

        for name in dir(manager):

            if name.startswith("_"):

                continue

            module = getattr(manager, name)

            if hasattr(module, "statistics"):

                try:

                    modules[name] = module.statistics()

                except Exception as exc:

                    logger.exception(

                        "Failed collecting metrics for %s",

                        name,

                        exc_info=exc,

                    )

        modules.update(self.metrics)

        return modules

    # --------------------------------------------------

    def summary(self) -> Dict[str, Any]:

        module_count = len(self.metrics)

        initialized = sum(

            1

            for values in self.metrics.values()

            if values.get("initialized")

        )

        return {

            "modules_tracked": module_count,

            "modules_initialized": initialized,

            "coverage": (

                round(

                    initialized / module_count,

                    3,

                )

                if module_count

                else 0.0

            ),

            "last_updated": self.last_updated,

        }

    # --------------------------------------------------

    def export(self) -> Dict[str, Any]:

        return {

            "generated": datetime.now(timezone.utc).isoformat(),

            "metrics": self.metrics.copy(),

        }

    # --------------------------------------------------

    def clear(self):

        self.metrics.clear()

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "tracked_modules": len(

                self.metrics

            ),

            "last_updated": self.last_updated,

        }