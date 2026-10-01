from __future__ import annotations
"""
HERCULE Smart Repair Engine

Smart Repair Manager

Main entry point for automatic project repair.
"""


from pathlib import Path
from typing import List

from .repair_engine import RepairEngine
from .repair_config import RepairConfig

# Built-in analyzers
from .analyzers.import_analyzer import ImportAnalyzer
from .analyzers.interface_analyzer import InterfaceAnalyzer
from .analyzers.syntax_analyzer import SyntaxAnalyzer
from .analyzers.placeholder_analyzer import PlaceholderAnalyzer
from .analyzers.dependency_analyzer import DependencyAnalyzer
from .analyzers.runtime_analyzer import RuntimeAnalyzer

# Built-in validators
from .validation.import_validator import ImportValidator
from .validation.interface_validator import InterfaceValidator
from .validation.runtime_validator import RuntimeValidator
from .validation.project_validator import ProjectValidator

# Backup
from .backup.backup_manager import BackupManager

# Rollback
from .backup.rollback_manager import RollbackManager


class SmartRepairManager:
    """
    Main controller of the Smart Repair Engine.

    Responsibilities
    ----------------

    • Scan project

    • Analyze problems

    • Backup files

    • Repair safely

    • Validate repairs

    • Rollback failures

    • Generate reports
    """

    def __init__(self, config: RepairConfig | None = None):

        self.config = config or RepairConfig()

        self.engine = RepairEngine(self.config)

        self.backup = BackupManager(self.config)

        self.rollback = RollbackManager(self.config)

        self._register_defaults()

    # -------------------------------------------------

    def _register_defaults(self):

        # ---------- Analyzers ----------

        self.engine.register_analyzer(
            SyntaxAnalyzer()
        )

        self.engine.register_analyzer(
            ImportAnalyzer()
        )

        self.engine.register_analyzer(
            InterfaceAnalyzer()
        )

        self.engine.register_analyzer(
            DependencyAnalyzer()
        )

        self.engine.register_analyzer(
            PlaceholderAnalyzer()
        )

        self.engine.register_analyzer(
            RuntimeAnalyzer()
        )

        # ---------- Validators ----------

        self.engine.register_validator(
            ImportValidator()
        )

        self.engine.register_validator(
            InterfaceValidator()
        )

        self.engine.register_validator(
            RuntimeValidator()
        )

        self.engine.register_validator(
            ProjectValidator()
        )

    # -------------------------------------------------

    def scan_file(self, file_path: Path):

        return self.engine.analyze(file_path)

    # -------------------------------------------------

    def repair_file(self, file_path: Path):

        print(f"\nScanning {file_path}")

        issues = self.engine.analyze(file_path)

        if not issues:

            print("No issues detected.")

            return True

        print(f"Found {len(issues)} issue(s).")

        backup = self.backup.create_backup(file_path)

        try:

            for issue in issues:

                print(

                    f"Repairing: "

                    f"{issue.get('type','Unknown')}"

                )

                # Patchers will be executed here
                # in Batch 3

            results = self.engine.validate(file_path)

            failed = any(
                not r.get("success", True)
                for r in results
            )

            if failed:

                raise RuntimeError(
                    "Validation failed."
                )

            self.engine.record_success(

                str(file_path),

                "Automatic repair",

                "Applied",

                str(backup)

            )

            print("Repair successful.")

            return True

        except Exception as exc:

            print(

                f"Repair failed: {exc}"

            )

            self.rollback.restore(

                backup,

                file_path

            )

            self.engine.record_failure(

                str(file_path),

                str(exc),

                "Rollback",

                str(backup)

            )

            return False

    # -------------------------------------------------

    def repair_project(self):

        root = self.config.project_root

        repaired = 0

        scanned = 0

        for file in root.rglob("*.py"):

            if any(

                folder in file.parts

                for folder in

                self.config.ignored_directories

            ):

                continue

            scanned += 1

            if self.repair_file(file):

                repaired += 1

        print("\n========== SUMMARY ==========")

        print(f"Files scanned : {scanned}")

        print(f"Files repaired: {repaired}")

        print("=============================")