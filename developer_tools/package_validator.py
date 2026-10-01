from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Package Validator

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from pathlib import Path
from typing import Dict, List


class PackageValidator:
    """
    Validates the package structure of
    the HERCULE project.

    Checks:

    • Missing __init__.py
    • Empty packages
    • Invalid package names
    • Python file statistics
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def validate(self) -> Dict:

        report = {

            "packages": 0,
            "python_files": 0,
            "missing_init": [],
            "empty_packages": [],
            "invalid_packages": [],

        }

        for directory in self.project_root.rglob("*"):

            if not directory.is_dir():

                continue

            py_files = list(directory.glob("*.py"))

            subdirs = list(directory.iterdir())

            if py_files:

                report["packages"] += 1

                init_file = directory / "__init__.py"

                if not init_file.exists():

                    report["missing_init"].append(

                        str(
                            directory.relative_to(
                                self.project_root
                            )
                        )

                    )

                report["python_files"] += len(py_files)

            if not py_files and not subdirs:

                report["empty_packages"].append(

                    str(
                        directory.relative_to(
                            self.project_root
                        )
                    )

                )

            if " " in directory.name:

                report["invalid_packages"].append(

                    str(
                        directory.relative_to(
                            self.project_root
                        )
                    )

                )

        return report

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.validate()

        print("\n========== Package Validator ==========\n")

        print(

            f"Packages        : {report['packages']}"

        )

        print(

            f"Python Files    : {report['python_files']}"

        )

        print(

            f"Missing Init    : {len(report['missing_init'])}"

        )

        print(

            f"Empty Packages  : {len(report['empty_packages'])}"

        )

        print(

            f"Invalid Names   : {len(report['invalid_packages'])}"

        )

        if report["missing_init"]:

            print("\nMissing __init__.py:\n")

            for package in report["missing_init"]:

                print(f" - {package}")

        if report["empty_packages"]:

            print("\nEmpty Packages:\n")

            for package in report["empty_packages"]:

                print(f" - {package}")

        if report["invalid_packages"]:

            print("\nInvalid Package Names:\n")

            for package in report["invalid_packages"]:

                print(f" - {package}")

        print("\n=======================================\n")