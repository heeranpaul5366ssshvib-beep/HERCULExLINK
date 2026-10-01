from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Developer Toolkit

Module: Code Quality Analyzer

Author : Heeran Paul
License : MIT
--------------------------------------------
"""


from pathlib import Path
from typing import Dict

from developer_tools.static_analysis import StaticAnalyzer
from developer_tools.duplicate_detector import DuplicateDetector
from developer_tools.dead_code_detector import DeadCodeDetector
from developer_tools.circular_dependency import CircularDependencyDetector
from developer_tools.package_validator import PackageValidator


class CodeQuality:
    """
    Computes an overall quality score
    for the HERCULE project.

    Score Range:
        90-100 : Excellent
        75-89  : Good
        60-74  : Fair
        <60    : Needs Improvement
    """

    def __init__(
        self,
        project_root: str | Path = ".",
    ) -> None:

        self.project_root = Path(project_root).resolve()

    # --------------------------------------------------

    def evaluate(self) -> Dict:

        static = StaticAnalyzer(
            self.project_root
        ).analyze()

        duplicate = DuplicateDetector(
            self.project_root
        ).scan()

        dead = DeadCodeDetector(
            self.project_root
        ).analyze()

        circular = CircularDependencyDetector(
            self.project_root
        ).analyze()

        packages = PackageValidator(
            self.project_root
        ).validate()

        score = 100

        score -= len(
            duplicate["duplicates"]
        ) * 2

        score -= len(
            dead["unused"]
        )

        score -= circular[
            "cycle_count"
        ] * 5

        score -= len(
            packages["missing_init"]
        ) * 2

        score = max(0, score)

        if score >= 90:

            rating = "Excellent"

        elif score >= 75:

            rating = "Good"

        elif score >= 60:

            rating = "Fair"

        else:

            rating = "Needs Improvement"

        return {

            "score": score,

            "rating": rating,

            "summary": {

                "python_files":
                    static.get(
                        "python_files",
                        0,
                    ),

                "duplicates":
                    duplicate[
                        "duplicate_groups"
                    ],

                "dead_code":
                    len(
                        dead["unused"]
                    ),

                "circular_dependencies":
                    circular[
                        "cycle_count"
                    ],

                "missing_init":
                    len(
                        packages[
                            "missing_init"
                        ]
                    ),

            },

        }

    # --------------------------------------------------

    def print_report(self) -> None:

        report = self.evaluate()

        print(
            "\n========== HERCULE Code Quality ==========\n"
        )

        print(
            f"Quality Score : {report['score']}/100"
        )

        print(
            f"Rating        : {report['rating']}"
        )

        print("\nMetrics\n")

        for key, value in report[
            "summary"
        ].items():

            print(
                f"{key:<25}: {value}"
            )

        print(
            "\n==========================================\n"
        )