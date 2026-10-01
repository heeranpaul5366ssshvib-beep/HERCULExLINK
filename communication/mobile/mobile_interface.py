from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Mobile Interface
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class MobileInterface:

    def __init__(self):

        self.connected = False

    ##################################################

    def connect(self):

        self.connected = True

    ##################################################

    def disconnect(self):

        self.connected = False

    ##################################################

    def send(

        self,

        message,

    ):

        return {

            "mobile": message,

        }

    ##################################################

    def status(self):

        return self.connected