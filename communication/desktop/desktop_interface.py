from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Desktop Interface
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class DesktopInterface:

    def __init__(self):

        self.running = False

    ##################################################

    def start(self):

        self.running = True

    ##################################################

    def stop(self):

        self.running = False

    ##################################################

    def send(

        self,

        message,

    ):

        return {

            "desktop": message,

        }

    ##################################################

    def status(self):

        return self.running