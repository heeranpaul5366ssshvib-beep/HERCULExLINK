from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Config Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import json
from pathlib import Path


class ConfigManager:

    def __init__(

        self,

        config_file=None,

    ):

        # Frozen (installed) apps must never write into Program Files:
        # operator configuration lives in the per-user config file.
        # An explicit config_file keeps working unchanged (dev/tests).
        if config_file is None:
            try:
                from system.paths import is_frozen, user_config_file
                config_file = (str(user_config_file()) if is_frozen()
                               else "config/hercule.json")
            except Exception:
                config_file = "config/hercule.json"

        self.config_file = Path(config_file)

        self.config = {}

    ##################################################

    def load(self):

        if self.config_file.exists():

            self.config = json.loads(

                self.config_file.read_text(

                    encoding="utf-8"

                )

            )

        return self.config

    ##################################################

    def save(self):

        self.config_file.parent.mkdir(

            parents=True,

            exist_ok=True,

        )

        self.config_file.write_text(

            json.dumps(

                self.config,

                indent=4,

            ),

            encoding="utf-8",

        )

    ##################################################

    def get(

        self,

        key,

        default=None,

    ):

        return self.config.get(

            key,

            default,

        )

    ##################################################

    def set(

        self,

        key,

        value,

    ):

        self.config[key] = value