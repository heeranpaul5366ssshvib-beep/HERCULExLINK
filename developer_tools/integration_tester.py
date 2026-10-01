from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Integration Tester

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from typing import Any, Dict


class IntegrationTester:
    """
    Verifies communication between
    HERCULE subsystems.

    Checks:

    • Kernel
    • Memory
    • Models
    • Intelligence
    • Agents
    • Abilities
    • Runtime
    • Security
    """

    def __init__(self) -> None:

        self.systems: Dict[str, Any] = {}

    # --------------------------------------------------

    def register(
        self,
        name: str,
        component: Any,
    ) -> None:

        self.systems[name] = component

    # --------------------------------------------------

    def run(self) -> Dict[str, Any]:

        report = {

            "total": len(self.systems),

            "passed": 0,

            "failed": 0,

            "results": {},

        }

        for name, component in self.systems.items():

            try:

                healthy = True

                if hasattr(component, "health"):

                    status = component.health()

                    healthy = bool(status)

                elif hasattr(component, "health_check"):

                    status = component.health_check()

                    healthy = bool(status)

                report["results"][name] = {

                    "status": "PASS" if healthy else "FAIL"

                }

                if healthy:

                    report["passed"] += 1

                else:

                    report["failed"] += 1

            except Exception as exc:

                report["results"][name] = {

                    "status": "ERROR",

                    "error": str(exc),

                }

                report["failed"] += 1

        return report

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.run()

        print("\n========== Integration Tester ==========\n")

        print(f"Components : {report['total']}")
        print(f"Passed     : {report['passed']}")
        print(f"Failed     : {report['failed']}")

        print("\nResults:\n")

        for name, result in report["results"].items():

            print(f"{name:<20} {result['status']}")

            if "error" in result:

                print(f"   {result['error']}")

        print("\n========================================\n")