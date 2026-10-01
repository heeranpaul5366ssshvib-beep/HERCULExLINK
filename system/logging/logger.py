from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Logger
--------------------------------------------
"""


from datetime import datetime
from pathlib import Path


class Logger:

    def __init__(

        self,

        log_file=None,

    ):

        # Frozen (installed) apps must never write into Program Files:
        # user logs live under %LOCALAPPDATA%\HERCULE\logs (same file as
        # system.paths.configure_file_logging). An explicit log_file
        # keeps working unchanged (dev/tests).
        if log_file is None:
            try:
                from system.paths import is_frozen, user_data_dir
                if is_frozen():
                    log_file = str(user_data_dir() / "logs" / "hercule.log")
                else:
                    log_file = "data/logs/hercule.log"
            except Exception:
                log_file = "data/logs/hercule.log"

        self.log_file = Path(log_file)

        try:
            self.log_file.parent.mkdir(

                parents=True,

                exist_ok=True,

            )
        except Exception:
            # Unwritable location (locked-down machine): file logging is
            # disabled rather than crashing the application at startup.
            self.log_file = None

    ##################################################

    def log(

        self,

        level,

        message,

    ):

        line = (

            f"[{datetime.now()}] "

            f"[{level}] "

            f"{message}\n"

        )

        if self.log_file is None:
            return

        try:
            with self.log_file.open(

                "a",

                encoding="utf-8",

            ) as file:

                file.write(line)
        except Exception:
            self.log_file = None

    ##################################################

    def info(

        self,

        message,

    ):

        self.log(

            "INFO",

            message,

        )

    ##################################################

    def warning(

        self,

        message,

    ):

        self.log(

            "WARNING",

            message,

        )

    ##################################################

    def error(

        self,

        message,

    ):

        self.log(

            "ERROR",

            message,

        )