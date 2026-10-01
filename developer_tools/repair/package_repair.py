from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Package Repair

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from pathlib import Path
from typing import Dict, List


class PackageRepair:
    """
    Repairs Python package structure.

    Features
    --------
    • Create missing __init__.py files
    • Remove invalid package names (report only)
    • Dry-run support
    • Detailed repair report

    Safe by default.
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def repair(
        self,
        dry_run: bool = True,
    ) -> Dict:

        created: List[str] = []
        warnings: List[str] = []

        for directory in self.project_root.rglob("*"):

            if not directory.is_dir():

                continue

            python_files = list(
                directory.glob("*.py")
            )

            if not python_files:

                continue

            init_file = directory / "__init__.py"

            if not init_file.exists():

                created.append(

                    str(

                        init_file.relative_to(
                            self.project_root
                        )

                    )

                )

                if not dry_run:

                    init_file.write_text(
                        '"""Package initializer."""\n',
                        encoding="utf-8",
                    )

            if " " in directory.name:

                warnings.append(

                    str(

                        directory.relative_to(
                            self.project_root
                        )

                    )

                )

        return {

            "dry_run":

                dry_run,

            "created":

                len(created),

            "created_files":

                created,

            "warnings":

                warnings,

        }

    # --------------------------------------------------

    def print_report(
        self,
        report: Dict,
    ) -> None:

        print(
            "\n========== Package Repair ==========\n"
        )

        print(
            f"Dry Run            : {report['dry_run']}"
        )

        print(
            f"Packages Repaired  : {report['created']}"
        )

        if report["created_files"]:

            print("\nCreated Files\n")

            for file in report["created_files"]:

                print(f" • {file}")

        if report["warnings"]:

            print("\nWarnings\n")

            for warning in report["warnings"]:

                print(f" • {warning}")

        if (
            not report["created_files"]
            and not report["warnings"]
        ):

            print(
                "\nPackage structure is healthy."
            )

        print(
            "\n====================================\n"
        )