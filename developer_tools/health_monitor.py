from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Health Monitor

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import time
from typing import Any, Dict


class HealthMonitor:
    """
    Monitors the health of all registered
    HERCULE components.

    Checks:

    • Availability
    • Health status
    • Response time
    • Error reporting
    """

    def __init__(self) -> None:

        self.components: Dict[str, Any] = {}

    # --------------------------------------------------

    def register(
        self,
        name: str,
        component: Any,
    ) -> None:

        self.components[name] = component

    # --------------------------------------------------

    def check(self) -> Dict[str, Any]:

        report = {

            "total": len(self.components),

            "healthy": 0,

            "unhealthy": 0,

            "results": {},

        }

        for name, component in self.components.items():

            start = time.perf_counter()

            try:

                status = True

                if hasattr(component, "health"):

                    status = bool(
                        component.health()
                    )

                elif hasattr(component, "health_check"):

                    status = bool(
                        component.health_check()
                    )

                elapsed = round(

                    time.perf_counter() - start,

                    4,

                )

                report["results"][name] = {

                    "status":
                        "HEALTHY"
                        if status
                        else "UNHEALTHY",

                    "response_time":
                        elapsed,

                }

                if status:

                    report["healthy"] += 1

                else:

                    report["unhealthy"] += 1

            except Exception as exc:

                report["results"][name] = {

                    "status": "ERROR",

                    "error": str(exc),

                }

                report["unhealthy"] += 1

        return report

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.check()

        print("\n========== Health Monitor ==========\n")

        print(f"Components : {report['total']}")
        print(f"Healthy    : {report['healthy']}")
        print(f"Unhealthy  : {report['unhealthy']}")

        print("\nComponent Status:\n")

        for name, result in report["results"].items():

            print(f"{name:<20} {result['status']}")

            if "response_time" in result:

                print(
                    f"   Response : "
                    f"{result['response_time']} sec"
                )

            if "error" in result:

                print(
                    f"   Error : "
                    f"{result['error']}"
                )

        print("\n====================================\n")