from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Repair Manager

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from pathlib import Path
from typing import Callable, Dict, List


class RepairManager:
    """
    Central manager for all repair modules.

    Responsibilities
    ----------------
    • Register repair modules
    • Execute selected repairs
    • Dry-run support
    • Generate repair summaries

    This manager NEVER performs repairs
    automatically.
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(
            project_root
        ).resolve()

        self.repairs: Dict[
            str,
            Callable
        ] = {}

        self.history: List[Dict] = []

    # --------------------------------------------------

    def register(

        self,

        name: str,

        repair_function: Callable,

    ) -> None:

        self.repairs[name] = repair_function

    # --------------------------------------------------

    def available_repairs(
        self,
    ) -> List[str]:

        return sorted(

            self.repairs.keys()

        )

    # --------------------------------------------------

    def execute(

        self,

        repair_name: str,

        dry_run: bool = True,

        **kwargs,

    ) -> Dict:

        if repair_name not in self.repairs:

            raise ValueError(

                f"Unknown repair: {repair_name}"

            )

        repair = self.repairs[
            repair_name
        ]

        result = repair(

            project_root=self.project_root,

            dry_run=dry_run,

            **kwargs,

        )

        record = {

            "repair":

                repair_name,

            "dry_run":

                dry_run,

            "result":

                result,

        }

        self.history.append(

            record

        )

        return record

    # --------------------------------------------------

    def history_report(
        self,
    ) -> List[Dict]:

        return list(

            self.history

        )

    # --------------------------------------------------

    def clear_history(
        self,
    ) -> None:

        self.history.clear()

    # --------------------------------------------------

    def print_report(
        self,
    ) -> None:

        print(

            "\n========== Repair Manager ==========\n"

        )

        print(

            f"Registered Repairs : "

            f"{len(self.repairs)}"

        )

        print(

            f"Executed Repairs   : "

            f"{len(self.history)}"

        )

        if self.repairs:

            print("\nAvailable Repairs\n")

            for repair in sorted(

                self.repairs

            ):

                print(

                    f" • {repair}"

                )

        print(

            "\n====================================\n"

        )