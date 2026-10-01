from __future__ import annotations
"""
HERCULE Smart Repair Engine

Repair History Manager
"""


from pathlib import Path
from datetime import datetime
import json


class RepairHistory:
    """
    Stores every repair operation performed by
    the Smart Repair Engine.
    """

    def __init__(self, history_file: Path):

        self.history_file = Path(history_file)

        self.history_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if not self.history_file.exists():

            self.history_file.write_text(
                "[]",
                encoding="utf-8"
            )

    # --------------------------------------------------

    def _load(self):

        try:

            return json.loads(
                self.history_file.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:

            return []

    # --------------------------------------------------

    def _save(self, history):

        self.history_file.write_text(

            json.dumps(
                history,
                indent=4
            ),

            encoding="utf-8"

        )

    # --------------------------------------------------

    def record(

        self,

        file_path: str,

        issue: str,

        action: str,

        status: str,

        backup: str | None = None

    ):

        history = self._load()

        history.append(

            {

                "timestamp":

                    datetime.now().isoformat(),

                "file":

                    file_path,

                "issue":

                    issue,

                "action":

                    action,

                "status":

                    status,

                "backup":

                    backup

            }

        )

        self._save(history)

    # --------------------------------------------------

    def all(self):

        return self._load()

    # --------------------------------------------------

    def latest(self, count=10):

        return self._load()[-count:]

    # --------------------------------------------------

    def clear(self):

        self._save([])