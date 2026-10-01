from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Project Scanner

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from pathlib import Path
from typing import Dict, List


class ProjectScanner:
    """
    Scans the HERCULE project directory and
    indexes all files and folders.

    Collects:

    • Directory structure
    • Python files
    • File sizes
    • File extensions
    • Statistics
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def scan(self) -> Dict:

        report = {

            "root": str(self.project_root),

            "directories": [],

            "files": [],

            "python_files": [],

            "extensions": {},

            "total_directories": 0,

            "total_files": 0,

        }

        for path in self.project_root.rglob("*"):

            if path.is_dir():

                report["directories"].append(

                    str(
                        path.relative_to(
                            self.project_root
                        )
                    )

                )

                report["total_directories"] += 1

            elif path.is_file():

                relative = str(

                    path.relative_to(
                        self.project_root
                    )

                )

                extension = path.suffix.lower()

                report["files"].append({

                    "path": relative,

                    "extension": extension,

                    "size": path.stat().st_size,

                })

                report["total_files"] += 1

                report["extensions"][extension] = (

                    report["extensions"].get(

                        extension,

                        0,

                    )

                    + 1

                )

                if extension == ".py":

                    report["python_files"].append(

                        relative

                    )

        return report

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.scan()

        print("\n========== Project Scanner ==========\n")

        print(
            f"Root         : {report['root']}"
        )

        print(
            f"Directories  : {report['total_directories']}"
        )

        print(
            f"Files        : {report['total_files']}"
        )

        print(
            f"Python Files : {len(report['python_files'])}"
        )

        print("\nExtensions:\n")

        for ext, count in sorted(

            report["extensions"].items()

        ):

            label = ext if ext else "<no extension>"

            print(

                f"{label:<15} {count}"

            )

        print(

            "\n=====================================\n"

        )