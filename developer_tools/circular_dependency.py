from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Circular Dependency Detector

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import ast
from pathlib import Path
from typing import Dict, List, Set


class CircularDependencyDetector:
    """
    Detects circular imports in the
    HERCULE project.

    Detects:

    • A -> B -> A
    • A -> B -> C -> A
    • Larger dependency cycles
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

        self.graph: Dict[str, Set[str]] = {}

    # --------------------------------------------------

    def analyze(self) -> Dict:

        self.graph.clear()

        for file in self.project_root.rglob("*.py"):

            module = self._module_name(file)

            imports = self._imports(file)

            self.graph[module] = imports

        cycles = []

        visited = set()

        for module in self.graph:

            self._dfs(

                module,

                [],

                visited,

                cycles,

            )

        return {

            "modules": len(self.graph),

            "cycles": cycles,

            "cycle_count": len(cycles),

        }

    # --------------------------------------------------

    def _module_name(
        self,
        file: Path,
    ) -> str:

        return str(

            file.relative_to(
                self.project_root
            )

        ).replace("\\", ".").replace("/", ".")[:-3]

    # --------------------------------------------------

    def _imports(
        self,
        file: Path,
    ) -> Set[str]:

        imports = set()

        try:

            tree = ast.parse(

                file.read_text(
                    encoding="utf-8"
                )

            )

            for node in ast.walk(tree):

                if isinstance(
                    node,
                    ast.Import,
                ):

                    for alias in node.names:

                        imports.add(alias.name)

                elif isinstance(
                    node,
                    ast.ImportFrom,
                ):

                    if node.module:

                        imports.add(node.module)

        except Exception:

            pass

        return imports

    # --------------------------------------------------

    def _dfs(

        self,

        module,

        path,

        visited,

        cycles,

    ):

        if module in path:

            cycle = path[path.index(module):] + [module]

            if cycle not in cycles:

                cycles.append(cycle)

            return

        if module in visited:

            return

        visited.add(module)

        path.append(module)

        for dependency in self.graph.get(module, []):

            if dependency in self.graph:

                self._dfs(

                    dependency,

                    path.copy(),

                    visited,

                    cycles,

                )

    # --------------------------------------------------

    def print_report(self):

        report = self.analyze()

        print("\n====== Circular Dependency ======\n")

        print(

            f"Modules : {report['modules']}"

        )

        print(

            f"Cycles  : {report['cycle_count']}"

        )

        if report["cycles"]:

            print("\nDetected Cycles:\n")

            for cycle in report["cycles"]:

                print(

                    " -> ".join(cycle)

                )

        else:

            print(

                "\nNo circular dependencies detected."

            )

        print(

            "\n=================================\n"

        )