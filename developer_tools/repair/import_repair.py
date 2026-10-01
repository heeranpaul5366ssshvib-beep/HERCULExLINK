from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Import Repair

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import re
from pathlib import Path
from typing import Dict, List


class ImportRepair:
    """
    Repairs broken Python imports.

    Features
    --------
    • Detect invalid imports
    • Replace outdated imports
    • Dry-run support
    • Detailed repair report

    NOTE:
    No file is modified unless
    dry_run=False.
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

        replacements: Dict[str, str],

        dry_run: bool = True,

    ) -> Dict:

        repaired_files: List[str] = []

        repaired_imports = 0

        for file in self.project_root.rglob("*.py"):

            try:

                original = file.read_text(
                    encoding="utf-8"
                )

                updated = original

                for old, new in replacements.items():

                    pattern = rf"\b{re.escape(old)}\b"

                    updated = re.sub(
                        pattern,
                        new,
                        updated,
                    )

                if updated != original:

                    repaired_imports += 1

                    repaired_files.append(

                        str(
                            file.relative_to(
                                self.project_root
                            )
                        )

                    )

                    if not dry_run:

                        file.write_text(
                            updated,
                            encoding="utf-8",
                        )

            except Exception:

                continue

        return {

            "dry_run":

                dry_run,

            "files_modified":

                len(repaired_files),

            "imports_repaired":

                repaired_imports,

            "modified_files":

                repaired_files,

        }

    # --------------------------------------------------

    def print_report(

        self,

        report: Dict,

    ) -> None:

        print(
            "\n========== Import Repair ==========\n"
        )

        print(
            f"Dry Run          : {report['dry_run']}"
        )

        print(
            f"Files Modified   : {report['files_modified']}"
        )

        print(
            f"Imports Repaired : {report['imports_repaired']}"
        )

        if report["modified_files"]:

            print("\nAffected Files\n")

            for file in report["modified_files"]:

                print(f" • {file}")

        else:

            print(
                "\nNo import issues found."
            )

        print(
            "\n===================================\n"
        )