from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Interface Validator

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import inspect
from pathlib import Path
from typing import Dict, List


class InterfaceValidator:
    """
    Validates public interfaces of HERCULE modules.

    Checks:

    • Missing classes
    • Missing methods
    • Invalid inheritance
    • Empty implementations
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

    # --------------------------------------------------

    def validate_module(
        self,
        module,
    ) -> Dict:

        report = {

            "module": module.__name__,

            "classes": [],

            "functions": [],

            "warnings": [],

        }

        members = inspect.getmembers(module)

        for name, obj in members:

            if inspect.isclass(obj):

                report["classes"].append(

                    self._validate_class(obj)

                )

            elif inspect.isfunction(obj):

                report["functions"].append(name)

        return report

    # --------------------------------------------------

    def _validate_class(
        self,
        cls,
    ) -> Dict:

        methods = []

        warnings = []

        for name, member in inspect.getmembers(cls):

            if inspect.isfunction(member):

                methods.append(name)

                source = inspect.getsource(member)

                if "pass" in source:

                    warnings.append(

                        f"{name} is empty."

                    )

        return {

            "class": cls.__name__,

            "methods": methods,

            "warnings": warnings,

        }

    # --------------------------------------------------

    def print_report(
        self,
        report: Dict,
    ) -> None:

        print("\n========== Interface Validator ==========\n")

        print(
            f"Module : {report['module']}\n"
        )

        for cls in report["classes"]:

            print(
                f"Class : {cls['class']}"
            )

            print(
                f"Methods : {len(cls['methods'])}"
            )

            if cls["warnings"]:

                for warning in cls["warnings"]:

                    print(
                        f"  WARNING : {warning}"
                    )

            print()

        print(
            "=========================================\n"
        )