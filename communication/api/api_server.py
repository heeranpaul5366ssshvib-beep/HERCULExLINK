from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: API Server
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class APIServer:

    def __init__(self):

        self.running = False

    ##################################################

    def start(self):

        self.running = True

    ##################################################

    def stop(self):

        self.running = False

    ##################################################

    def status(self):

        return self.running