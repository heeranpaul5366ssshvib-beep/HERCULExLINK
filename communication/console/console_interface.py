from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Console Interface
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class ConsoleInterface:

    def start(self):

        print("=" * 60)
        print("HERCULE AI Operating System")
        print("=" * 60)

    ##################################################

    def input(self):

        return input("HERCULE > ")

    ##################################################

    def output(

        self,

        message,

    ):

        print(message)

    ##################################################

    def stop(self):

        print("Console Closed")