from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Diagnostics

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from datetime import datetime
from typing import Dict, Any

from developer_tools.architecture_validator import (
    ArchitectureValidator,
)
from developer_tools.dependency_checker import (
    DependencyChecker,
)
from developer_tools.import_checker import (
    ImportChecker,
)


class Diagnostics:
    """
    Executes complete diagnostics
    for the HERCULE project.

    Coordinates all validation modules
    and produces a unified report.
    """

    def __init__(self) -> None:

        self.architecture = ArchitectureValidator()

        self.dependencies = DependencyChecker()

        self.imports = ImportChecker()

    # --------------------------------------------------

    def run(self) -> Dict[str, Any]:

        report = {

            "timestamp":
                datetime.now().isoformat(),

            "architecture":
                self.architecture.validate(),

            "dependencies":
                self.dependencies.check(),

            "imports":
                self.imports.check(),

        }

        passed = 0
        failed = 0

        for result in report.values():

            if isinstance(result, dict):

                if result.get("success", False):

                    passed += 1

                else:

                    failed += 1

        report["summary"] = {

            "passed": passed,

            "failed": failed,

            "status": (
                "PASSED"
                if failed == 0
                else "FAILED"
            ),

        }

        return report

    # --------------------------------------------------

    def quick_check(self):

        return {

            "architecture":
                self.architecture.validate().get(
                    "success",
                    False,
                ),

            "dependencies":
                self.dependencies.check().get(
                    "success",
                    False,
                ),

            "imports":
                self.imports.check().get(
                    "success",
                    False,
                ),

        }

    # --------------------------------------------------

    def print_report(self):

        report = self.run()

        print("\n========== HERCULE DIAGNOSTICS ==========\n")

        print(
            f"Timestamp : {report['timestamp']}"
        )

        print(
            f"Architecture : "
            f"{report['architecture']['success']}"
        )

        print(
            f"Dependencies : "
            f"{report['dependencies']['success']}"
        )

        print(
            f"Imports : "
            f"{report['imports']['success']}"
        )

        print("\nSummary")

        print(
            f"Passed : {report['summary']['passed']}"
        )

        print(
            f"Failed : {report['summary']['failed']}"
        )

        print(
            f"Status : {report['summary']['status']}"
        )

        print(
            "\n=========================================\n"
        )