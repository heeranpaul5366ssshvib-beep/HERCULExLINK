from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Static Analysis

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import ast
from pathlib import Path
from typing import Dict, List


class StaticAnalysis:
    """
    Performs static analysis on the HERCULE
    source code without executing it.

    Checks:

    • Syntax errors
    • Large functions
    • Large classes
    • TODO markers
    • FIXME markers
    • Empty files
    """

    MAX_FUNCTION_LINES = 100
    MAX_CLASS_METHODS = 20

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def analyze(self) -> Dict:

        report = {

            "files": 0,

            "issues": [],

            "syntax_errors": 0,

        }

        for file in self.project_root.rglob("*.py"):

            report["files"] += 1

            self._analyze_file(
                file,
                report,
            )

        return report

    # --------------------------------------------------

    def _analyze_file(
        self,
        file: Path,
        report: Dict,
    ) -> None:

        try:

            source = file.read_text(
                encoding="utf-8"
            )

            if not source.strip():

                report["issues"].append({

                    "file": str(
                        file.relative_to(
                            self.project_root
                        )
                    ),

                    "type": "Empty File",

                })

                return

            if "TODO" in source:

                report["issues"].append({

                    "file": str(
                        file.relative_to(
                            self.project_root
                        )
                    ),

                    "type": "TODO Found",

                })

            if "FIXME" in source:

                report["issues"].append({

                    "file": str(
                        file.relative_to(
                            self.project_root
                        )
                    ),

                    "type": "FIXME Found",

                })

            tree = ast.parse(source)

            for node in ast.walk(tree):

                if isinstance(
                    node,
                    ast.FunctionDef,
                ):

                    if hasattr(node, "end_lineno"):

                        length = (

                            node.end_lineno
                            - node.lineno
                            + 1

                        )

                        if length > self.MAX_FUNCTION_LINES:

                            report["issues"].append({

                                "file": str(
                                    file.relative_to(
                                        self.project_root
                                    )
                                ),

                                "type": "Large Function",

                                "name": node.name,

                                "lines": length,

                            })

                elif isinstance(
                    node,
                    ast.ClassDef,
                ):

                    methods = [

                        n for n in node.body

                        if isinstance(
                            n,
                            ast.FunctionDef,
                        )

                    ]

                    if len(methods) > self.MAX_CLASS_METHODS:

                        report["issues"].append({

                            "file": str(
                                file.relative_to(
                                    self.project_root
                                )
                            ),

                            "type": "Large Class",

                            "name": node.name,

                            "methods": len(methods),

                        })

        except SyntaxError as exc:

            report["syntax_errors"] += 1

            report["issues"].append({

                "file": str(
                    file.relative_to(
                        self.project_root
                    )
                ),

                "type": "Syntax Error",

                "line": exc.lineno,

                "message": str(exc),

            })

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.analyze()

        print("\n========== Static Analysis ==========\n")

        print(f"Files Analysed : {report['files']}")

        print(f"Syntax Errors  : {report['syntax_errors']}")

        print(f"Issues Found   : {len(report['issues'])}")

        if report["issues"]:

            print("\nDetected Issues:\n")

            for issue in report["issues"]:

                print(issue)

        else:

            print("\nNo issues detected.")

        print("\n=====================================\n")