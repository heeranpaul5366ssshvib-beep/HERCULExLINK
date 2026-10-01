from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Repair Report

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class RepairReport:
    """
    Generates a unified repair report.

    Collects repair results from:

    • Import Repair
    • Package Repair
    • Interface Repair

    Supports:

    • JSON export
    • Text summary
    • Timestamped reports
    """

    def __init__(self) -> None:

        self.timestamp = datetime.now()

        self.entries: List[Dict] = []

    # --------------------------------------------------

    def add_result(

        self,

        repair_name: str,

        result: Dict,

    ) -> None:

        self.entries.append(

            {

                "repair":

                    repair_name,

                "result":

                    result,

            }

        )

    # --------------------------------------------------

    def generate(self) -> Dict:

        total_repairs = 0

        total_issues = 0

        dry_run = True

        for entry in self.entries:

            result = entry["result"]

            dry_run &= result.get(

                "dry_run",

                True,

            )

            total_repairs += result.get(

                "repairs_applied",

                result.get(

                    "imports_repaired",

                    result.get(

                        "created",

                        0,

                    ),

                ),

            )

            total_issues += result.get(

                "issues_found",

                0,

            )

        return {

            "timestamp":

                self.timestamp.isoformat(),

            "dry_run":

                dry_run,

            "modules":

                len(self.entries),

            "issues":

                total_issues,

            "repairs":

                total_repairs,

            "details":

                self.entries,

        }

    # --------------------------------------------------

    def export_json(

        self,

        file: str | Path,

    ) -> None:

        report = self.generate()

        Path(file).write_text(

            json.dumps(

                report,

                indent=4,

            ),

            encoding="utf-8",

        )

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.generate()

        print(

            "\n========== Repair Report ==========\n"

        )

        print(

            f"Timestamp : "

            f"{report['timestamp']}"

        )

        print(

            f"Dry Run   : "

            f"{report['dry_run']}"

        )

        print(

            f"Modules   : "

            f"{report['modules']}"

        )

        print(

            f"Issues    : "

            f"{report['issues']}"

        )

        print(

            f"Repairs   : "

            f"{report['repairs']}"

        )

        print("\nRepair Modules\n")

        for entry in report["details"]:

            print(

                f"• {entry['repair']}"

            )

        print(

            "\n===================================\n"

        )