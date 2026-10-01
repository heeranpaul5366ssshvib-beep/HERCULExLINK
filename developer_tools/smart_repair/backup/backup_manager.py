from __future__ import annotations
"""
HERCULE Smart Repair Engine

Backup Manager
"""


import shutil
from datetime import datetime
from pathlib import Path

from ..repair_config import RepairConfig


class BackupManager:
    """
    Creates timestamped backups before
    any repair operation.
    """

    def __init__(self, config: RepairConfig):

        self.config = config

        self.root = self.config.backup_path()

        self.root.mkdir(
            parents=True,
            exist_ok=True
        )

    # --------------------------------------------------

    def create_backup(self, file_path: Path) -> Path:

        file_path = Path(file_path)

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        relative = file_path.relative_to(
            self.config.project_root
        )

        backup = (
            self.root /
            timestamp /
            relative
        )

        backup.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        shutil.copy2(file_path, backup)

        return backup