from __future__ import annotations
"""
HERCULE Smart Repair Engine

Repair Report
"""


from pathlib import Path
from datetime import datetime


class RepairReport:

    """
    Creates human-readable repair reports.
    """

    def __init__(self):

        self.entries = []

    # --------------------------------------------------

    def add(

        self,

        severity,

        file,

        issue,

        solution,

        status

    ):

        self.entries.append(

            {

                "severity": severity,

                "file": file,

                "issue": issue,

                "solution": solution,

                "status": status

            }

        )

    # --------------------------------------------------

    def summary(self):

        return {

            "total": len(self.entries),

            "critical":

                sum(
                    1
                    for e in self.entries
                    if e["severity"] == "CRITICAL"
                ),

            "warnings":

                sum(
                    1
                    for e in self.entries
                    if e["severity"] == "WARNING"
                ),

            "fixed":

                sum(
                    1
                    for e in self.entries
                    if e["status"] == "FIXED"
                ),

            "failed":

                sum(
                    1
                    for e in self.entries
                    if e["status"] == "FAILED"
                )

        }

    # --------------------------------------------------

    def save(self, filename):

        filename = Path(filename)

        filename.parent.mkdir(

            parents=True,

            exist_ok=True

        )

        report = []

        report.append(
            "# HERCULE Smart Repair Report\n"
        )

        report.append(

            f"Generated: "

            f"{datetime.now().isoformat()}\n"

        )

        report.append("---\n")

        summary = self.summary()

        report.append(
            f"Total Issues : {summary['total']}\n"
        )

        report.append(
            f"Critical : {summary['critical']}\n"
        )

        report.append(
            f"Warnings : {summary['warnings']}\n"
        )

        report.append(
            f"Fixed : {summary['fixed']}\n"
        )

        report.append(
            f"Failed : {summary['failed']}\n\n"
        )

        for item in self.entries:

            report.append(
                "---------------------------------\n"
            )

            report.append(
                f"Severity : {item['severity']}\n"
            )

            report.append(
                f"File : {item['file']}\n"
            )

            report.append(
                f"Issue : {item['issue']}\n"
            )

            report.append(
                f"Solution : {item['solution']}\n"
            )

            report.append(
                f"Status : {item['status']}\n\n"
            )

        filename.write_text(

            "".join(report),

            encoding="utf-8"

        )