from __future__ import annotations
"""
Rollback Manager
"""


import shutil
from pathlib import Path

from ..repair_config import RepairConfig


class RollbackManager:

    """
    Restores the original file if a repair
    fails validation.
    """

    def __init__(self, config: RepairConfig):

        self.config = config

    # --------------------------------------------------

    def restore(

        self,

        backup_file: Path,

        target_file: Path

    ) -> bool:

        backup_file = Path(backup_file)

        target_file = Path(target_file)

        if not backup_file.exists():

            return False

        shutil.copy2(

            backup_file,

            target_file

        )

        return True