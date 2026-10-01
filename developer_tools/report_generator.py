from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Report Generator

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


class ReportGenerator:
    """
    Generates a comprehensive project report
    from all developer toolkit modules.

    Supported Formats

    • Console
    • JSON
    • Markdown

    The report is read-only and never modifies
    the HERCULE project.
    """

    def __init__(self) -> None:

        self.sections: Dict[str, Any] = {}

        self.timestamp = datetime.now()

    # --------------------------------------------------

    def add_section(

        self,

        name: str,

        data: Dict,

    ) -> None:

        self.sections[name] = data

    # --------------------------------------------------

    def overall_score(self) -> int:

        score = 100

        for section in self.sections.values():

            if not isinstance(section, dict):
                continue

            score -= section.get("errors", 0)

            score -= section.get("warnings", 0)

            score -= section.get("critical", 0) * 5

        return max(0, score)

    # --------------------------------------------------

    def readiness(self) -> str:

        score = self.overall_score()

        if score >= 95:
            return "Production Ready"

        if score >= 85:
            return "Release Candidate"

        if score >= 70:
            return "Development Stable"

        if score >= 50:
            return "Needs Improvements"

        return "Not Ready"

    # --------------------------------------------------

    def generate(self) -> Dict:

        return {

            "timestamp":

                self.timestamp.isoformat(),

            "overall_score":

                self.overall_score(),

            "status":

                self.readiness(),

            "sections":

                self.sections,

        }

    # --------------------------------------------------

    def export_json(

        self,

        filename: str | Path,

    ) -> None:

        Path(filename).write_text(

            json.dumps(

                self.generate(),

                indent=4,

            ),

            encoding="utf-8",

        )

    # --------------------------------------------------

    def export_markdown(

        self,

        filename: str | Path,

    ) -> None:

        report = self.generate()

        lines = [

            "# HERCULE Project Report",

            "",

            f"Generated : {report['timestamp']}",

            "",

            f"Overall Score : {report['overall_score']}/100",

            f"Status : {report['status']}",

            "",

            "---",

            "",

        ]

        for section, values in report["sections"].items():

            lines.append(f"## {section}")

            lines.append("")

            if isinstance(values, dict):

                for key, value in values.items():

                    lines.append(f"- **{key}** : {value}")

            else:

                lines.append(str(values))

            lines.append("")

        Path(filename).write_text(

            "\n".join(lines),

            encoding="utf-8",

        )

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.generate()

        print("\n========== HERCULE PROJECT REPORT ==========\n")

        print(

            f"Generated : "

            f"{report['timestamp']}"

        )

        print(

            f"Score     : "

            f"{report['overall_score']}/100"

        )

        print(

            f"Status    : "

            f"{report['status']}"

        )

        print("\nSections\n")

        for section in report["sections"]:

            print(f"• {section}")

        print("\n============================================\n")