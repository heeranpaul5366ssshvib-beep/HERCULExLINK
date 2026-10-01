from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Architecture Validator

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from pathlib import Path
from typing import Dict, List


class ArchitectureValidator:
    """
    Validates the HERCULE project
    architecture.

    Checks:

    • Required directories
    • Required files
    • Package structure
    • Overall integrity
    """

    REQUIRED_DIRECTORIES = [

        "abilities",
        "agents",
        "boot",
        "brain",
        "cognition",
        "communication",
        "developer_tools",
        "engineering",
        "intelligence",
        "kernel",
        "knowledge",
        "memory",
        "models",
        "orchestrator",
        "perception",
        "plugins",
        "robotics",
        "runtime",
        "security",
        "simulation",
        "system",

    ]

    REQUIRED_FILES = [

        "boot.py",
        "README.md",
        "requirements.txt",
        "pyproject.toml",

    ]

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def validate(self) -> Dict:

        missing_dirs = self._check_directories()

        missing_files = self._check_files()

        success = (

            len(missing_dirs) == 0

            and

            len(missing_files) == 0

        )

        return {

            "success": success,

            "project_root": str(
                self.project_root
            ),

            "missing_directories":
                missing_dirs,

            "missing_files":
                missing_files,

            "checked_directories":
                len(self.REQUIRED_DIRECTORIES),

            "checked_files":
                len(self.REQUIRED_FILES),

        }

    # --------------------------------------------------

    def _check_directories(
        self,
    ) -> List[str]:

        missing = []

        for directory in self.REQUIRED_DIRECTORIES:

            path = self.project_root / directory

            if not path.exists():

                missing.append(directory)

        return missing

    # --------------------------------------------------

    def _check_files(
        self,
    ) -> List[str]:

        missing = []

        for filename in self.REQUIRED_FILES:

            path = self.project_root / filename

            if not path.exists():

                missing.append(filename)

        return missing

    # --------------------------------------------------

    def print_report(self):

        report = self.validate()

        print("\n========== Architecture ==========\n")

        print(
            f"Project : {report['project_root']}"
        )

        print(
            f"Status  : "
            f"{'PASSED' if report['success'] else 'FAILED'}"
        )

        print()

        if report["missing_directories"]:

            print("Missing Directories:")

            for item in report[
                "missing_directories"
            ]:

                print(f" - {item}")

        if report["missing_files"]:

            print("\nMissing Files:")

            for item in report[
                "missing_files"
            ]:

                print(f" - {item}")

        if report["success"]:

            print(
                "Architecture validation successful."
            )

        print(
            "\n==================================\n"
        )