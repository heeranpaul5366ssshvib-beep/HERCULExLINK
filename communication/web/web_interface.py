from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Web Interface
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class WebInterface:

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

            "web": message,

        }

    ##################################################

    def status(self):

        return self.running