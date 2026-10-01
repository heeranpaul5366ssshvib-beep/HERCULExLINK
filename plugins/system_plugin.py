from __future__ import annotations
"""
--------------------------------------------
System Plugin
--------------------------------------------
"""


from plugin_sdk.plugin import Plugin


class SystemPlugin(Plugin):

    name = "system"

    version = "1.0.0"

    author = "HERCULE"

    ##################################################

    def __init__(

        self,

        system=None,

    ):

        self.system = system

    ##################################################

    def execute(

        self,

    ):

        if self.system is None:

            return {

                "status": "System Manager not connected"

            }

        return self.system.status()