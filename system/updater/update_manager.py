from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Update Manager
--------------------------------------------
"""



class UpdateManager:

    def __init__(self):

        try:
            from system.version import __version__ as app_version
        except Exception:
            app_version = "1.0.0"
        self.version = app_version

    ##################################################

    def current_version(self):

        return self.version

    ##################################################

    def check(self):

        return {

            "update_available": False,

            "latest": self.version,

        }

    ##################################################

    def install(self):

        return True