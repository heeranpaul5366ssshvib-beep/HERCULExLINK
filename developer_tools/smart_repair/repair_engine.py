from __future__ import annotations
"""
HERCULE Smart Repair Engine

Core Repair Engine
"""


from pathlib import Path
from typing import Dict, List, Optional

from .repair_config import RepairConfig
from .repair_history import RepairHistory
from .repair_report import RepairReport


class RepairEngine:
    """
    Central engine responsible for coordinating
    analysis, repair, validation and rollback.
    """

    def __init__(self, config: Optional[RepairConfig] = None):

        self.config = config or RepairConfig()

        history_file = (
            self.config.backup_path() /
            "repair_history.json"
        )

        self.history = RepairHistory(history_file)

        self.report = RepairReport()

        self.analyzers = []

        self.patchers = []

        self.validators = []

    # -------------------------------------------------

    def register_analyzer(self, analyzer):

        self.analyzers.append(analyzer)

    # -------------------------------------------------

    def register_patcher(self, patcher):

        self.patchers.append(patcher)

    # -------------------------------------------------

    def register_validator(self, validator):

        self.validators.append(validator)

    # -------------------------------------------------

    def analyze(self, file_path: Path) -> List[Dict]:

        issues = []

        for analyzer in self.analyzers:

            try:

                result = analyzer.scan(file_path)

                if result:

                    issues.extend(result)

            except Exception as exc:

                self.report.add(

                    severity="WARNING",

                    file=str(file_path),

                    issue=str(exc),

                    solution="Analyzer execution failed",

                    status="FAILED",

                )

        return issues

    # -------------------------------------------------

    def create_plan(self, issues):

        plan = []

        for issue in issues:

            plan.append(

                {

                    "issue": issue,

                    "status": "PENDING"

                }

            )

        return plan

    # -------------------------------------------------

    def repair(self, file_path: Path):

        issues = self.analyze(file_path)

        plan = self.create_plan(issues)

        return plan

    # -------------------------------------------------

    def validate(self, file_path: Path):

        results = []

        for validator in self.validators:

            try:

                results.append(

                    validator.validate(file_path)

                )

            except Exception as exc:

                results.append(

                    {

                        "validator":

                            validator.__class__.__name__,

                        "success": False,

                        "reason": str(exc),

                    }

                )

        return results

    # -------------------------------------------------

    def record_success(

        self,

        file_path,

        issue,

        action,

        backup=None,

    ):

        self.history.record(

            file_path=file_path,

            issue=issue,

            action=action,

            status="SUCCESS",

            backup=backup,

        )

    # -------------------------------------------------

    def record_failure(

        self,

        file_path,

        issue,

        action,

        backup=None,

    ):

        self.history.record(

            file_path=file_path,

            issue=issue,

            action=action,

            status="FAILED",

            backup=backup,

        )

    # -------------------------------------------------

    def clear(self):

        self.report.entries.clear()