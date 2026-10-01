from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Toolkit

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from typing import Dict, Any

from developer_tools.diagnostics import Diagnostics
from developer_tools.architecture_validator import (
    ArchitectureValidator,
)
from developer_tools.dependency_checker import (
    DependencyChecker,
)
from developer_tools.import_checker import (
    ImportChecker,
)


class DeveloperToolkit:
    """
    Master controller of the HERCULE
    Developer Toolkit.

    Responsible for coordinating every
    validator, scanner, tester and
    reporting module.
    """

    def __init__(self) -> None:

        self.diagnostics = Diagnostics()

        self.architecture = ArchitectureValidator()

        self.dependencies = DependencyChecker()

        self.imports = ImportChecker()

    # --------------------------------------------------

    def run_all(self) -> Dict[str, Any]:
        """
        Execute every available validator.
        """

        results = {

            "diagnostics":
                self.diagnostics.run(),

            "architecture":
                self.architecture.validate(),

            "dependencies":
                self.dependencies.check(),

            "imports":
                self.imports.check(),

        }

        return results

    # --------------------------------------------------

    def run_diagnostics(self):

        return self.diagnostics.run()

    # --------------------------------------------------

    def validate_architecture(self):

        return self.architecture.validate()

    # --------------------------------------------------

    def check_dependencies(self):

        return self.dependencies.check()

    # --------------------------------------------------

    def check_imports(self):

        return self.imports.check()

    # --------------------------------------------------

    def summary(self):

        report = self.run_all()

        total = len(report)

        passed = sum(
            1
            for result in report.values()
            if result.get("success", False)
        )

        failed = total - passed

        return {

            "total_checks": total,

            "passed": passed,

            "failed": failed,

            "results": report,

        }