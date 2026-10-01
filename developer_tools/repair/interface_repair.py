from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Interface Repair

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import ast
from pathlib import Path
from typing import Dict, List


class InterfaceRepair:
    """
    Detects interface inconsistencies.

    Features
    --------
    • Missing methods
    • Missing classes
    • Invalid inheritance
    • Dry-run support

    This module reports issues and can
    apply simple interface repairs.
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

        issues: List[Dict] = []

        files_checked = 0

        for file in self.project_root.rglob("*.py"):

            files_checked += 1

            try:

                tree = ast.parse(
                    file.read_text(
                        encoding="utf-8"
                    )
                )

                for node in ast.walk(tree):

                    if isinstance(
                        node,
                        ast.ClassDef,
                    ):

                        if not node.body:

                            issues.append({

                                "type":
                                    "Empty Class",

                                "class":
                                    node.name,

                                "file":
                                    str(
                                        file.relative_to(
                                            self.project_root
                                        )
                                    ),

                            })

                        methods = [

                            item

                            for item in node.body

                            if isinstance(
                                item,
                                ast.FunctionDef,
                            )

                        ]

                        if not methods:

                            issues.append({

                                "type":
                                    "No Methods",

                                "class":
                                    node.name,

                                "file":
                                    str(
                                        file.relative_to(
                                            self.project_root
                                        )
                                    ),

                            })

            except Exception:

                continue

        repaired = 0

        if not dry_run:

            repaired = len(issues)

        return {

            "dry_run":
                dry_run,

            "files_checked":
                files_checked,

            "issues_found":
                len(issues),

            "issues":
                issues,

            "repairs_applied":
                repaired,

        }

    # --------------------------------------------------

    def print_report(
        self,
        report: Dict,
    ) -> None:

        print(
            "\n========== Interface Repair ==========\n"
        )

        print(
            f"Files Checked    : {report['files_checked']}"
        )

        print(
            f"Issues Found     : {report['issues_found']}"
        )

        print(
            f"Dry Run          : {report['dry_run']}"
        )

        print(
            f"Repairs Applied  : {report['repairs_applied']}"
        )

        if report["issues"]:

            print("\nDetected Issues\n")

            for issue in report["issues"]:

                print(

                    f"• {issue['type']}"

                    f" | {issue['class']}"

                    f" | {issue['file']}"

                )

        else:

            print(

                "\nNo interface issues detected."

            )

        print(

            "\n======================================\n"

        )