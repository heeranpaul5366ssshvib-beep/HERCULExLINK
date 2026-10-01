from __future__ import annotations
"""
--------------------------------------------
File Plugin
--------------------------------------------
"""


from pathlib import Path

from plugin_sdk.plugin import Plugin


class FilePlugin(Plugin):

    name = "files"

    version = "1.0.0"

    author = "HERCULE"

    ##################################################

    def execute(

        self,

        path,

    ):

        path = Path(path)

        if not path.exists():

            return None

        return path.read_text(

            encoding="utf-8",

            errors="ignore",

        )