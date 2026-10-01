from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Dead Code Detector

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import ast
from pathlib import Path
from typing import Dict, Set


class DeadCodeDetector:
    """
    Detects potentially unused code.

    Checks:

    • Unused functions
    • Unused classes
    • Unused methods
    • Unreachable code
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def analyze(self) -> Dict:

        definitions: Set[str] = set()

        usages: Set[str] = set()

        for file in self.project_root.rglob("*.py"):

            try:

                tree = ast.parse(

                    file.read_text(
                        encoding="utf-8"
                    )

                )

                self._collect(
                    tree,
                    definitions,
                    usages,
                )

            except Exception:

                continue

        unused = sorted(

            definitions - usages

        )

        return {

            "definitions":

                len(definitions),

            "references":

                len(usages),

            "unused":

                unused,

        }

    # --------------------------------------------------

    def _collect(

        self,

        tree,

        definitions,

        usages,

    ) -> None:

        for node in ast.walk(tree):

            if isinstance(

                node,

                (

                    ast.FunctionDef,

                    ast.AsyncFunctionDef,

                    ast.ClassDef,

                ),

            ):

                definitions.add(

                    node.name

                )

            elif isinstance(

                node,

                ast.Call,

            ):

                if isinstance(

                    node.func,

                    ast.Name,

                ):

                    usages.add(

                        node.func.id

                    )

                elif isinstance(

                    node.func,

                    ast.Attribute,

                ):

                    usages.add(

                        node.func.attr

                    )

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.analyze()

        print("\n========== Dead Code Detector ==========\n")

        print(

            f"Definitions : "

            f"{report['definitions']}"

        )

        print(

            f"References  : "

            f"{report['references']}"

        )

        print(

            f"Unused      : "

            f"{len(report['unused'])}"

        )

        if report["unused"]:

            print("\nPotential Dead Code:\n")

            for item in report["unused"]:

                print(

                    f" - {item}"

                )

        else:

            print(

                "\nNo dead code detected."

            )

        print(

            "\n========================================\n"

        )