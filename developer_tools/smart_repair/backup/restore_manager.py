from __future__ import annotations
"""
Restore Manager

Allows restoring backups manually.
"""


import shutil
from pathlib import Path

from ..repair_config import RepairConfig


class RestoreManager:

    def __init__(self, config: RepairConfig):

        self.config = config

    # --------------------------------------------------

    def restore(

        self,

        backup: Path,

        destination: Path

    ) -> bool:

        backup = Path(backup)

        destination = Path(destination)

        if not backup.exists():

            return False

        destination.parent.mkdir(

            parents=True,

            exist_ok=True

        )

        shutil.copy2(

            backup,

            destination

        )

        return True

    # --------------------------------------------------

    def available_backups(self):

        backups = []

        root = self.config.backup_path()

        if not root.exists():

            return backups

        for file in root.rglob("*.py"):

            backups.append(file)

        return sorted(backups)