from __future__ import annotations
"""
--------------------------------------------
Terminal Plugin
--------------------------------------------
"""


import subprocess

from plugin_sdk.plugin import Plugin


class TerminalPlugin(Plugin):

    name = "terminal"

    version = "1.0.0"

    author = "HERCULE"

    ##################################################

    def execute(

        self,

        command,

    ):

        result = subprocess.run(

            command,

            shell=True,

            capture_output=True,

            text=True,

        )

        return result.stdout