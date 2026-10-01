from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Privacy Manager
--------------------------------------------
"""



class PrivacyManager:

    def __init__(self):

        self.private_mode = True

    ##################################################

    def enable(self):

        self.private_mode = True

    ##################################################

    def disable(self):

        self.private_mode = False

    ##################################################

    def status(self):

        return self.private_mode