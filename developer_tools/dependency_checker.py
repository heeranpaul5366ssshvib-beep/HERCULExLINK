from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Dependency Checker

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import importlib
from pathlib import Path
from typing import Dict, List


class DependencyChecker:
    """
    Validates project dependencies.

    Checks:

    • Installed Python packages
    • requirements.txt
    • Missing dependencies
    • Import availability
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

        self.requirements_file = (
            self.project_root / "requirements.txt"
        )

    # --------------------------------------------------

    def check(self) -> Dict:

        requirements = self._load_requirements()

        missing = []

        installed = []

        for package in requirements:

            if self._is_installed(package):

                installed.append(package)

            else:

                missing.append(package)

        return {

            "success":
                len(missing) == 0,

            "requirements":
                len(requirements),

            "installed":
                installed,

            "missing":
                missing,

        }

    # --------------------------------------------------

    def _load_requirements(
        self,
    ) -> List[str]:

        packages = []

        if not self.requirements_file.exists():

            return packages

        with open(
            self.requirements_file,
            "r",
            encoding="utf-8",
        ) as file:

            for line in file:

                line = line.strip()

                if (
                    not line
                    or line.startswith("#")
                ):

                    continue

                package = (
                    line.split("==")[0]
                    .split(">=")[0]
                    .split("<=")[0]
                    .strip()
                )

                packages.append(package)

        return packages

    # --------------------------------------------------

    @staticmethod
    def _is_installed(
        package: str,
    ) -> bool:

        try:

            importlib.import_module(package)

            return True

        except Exception:

            return False

    # --------------------------------------------------

    def print_report(self):

        report = self.check()

        print("\n========== Dependencies ==========\n")

        print(
            f"Requirements : "
            f"{report['requirements']}"
        )

        print(
            f"Installed    : "
            f"{len(report['installed'])}"
        )

        print(
            f"Missing      : "
            f"{len(report['missing'])}"
        )

        if report["missing"]:

            print("\nMissing Packages:\n")

            for package in report["missing"]:

                print(f" - {package}")

        else:

            print(
                "\nAll dependencies satisfied."
            )

        print(
            "\n==================================\n"
        )