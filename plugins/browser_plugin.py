from __future__ import annotations
"""
--------------------------------------------
Browser Plugin
--------------------------------------------
"""


import webbrowser

from plugin_sdk.plugin import Plugin


class BrowserPlugin(Plugin):

    name = "browser"

    version = "1.0.0"

    author = "HERCULE"

    ##################################################

    def execute(

        self,

        url,

    ):

        webbrowser.open(

            url,

        )

        return True