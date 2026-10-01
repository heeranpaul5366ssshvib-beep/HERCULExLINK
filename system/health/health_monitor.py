from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Health Monitor
--------------------------------------------
"""



class HealthMonitor:

    def __init__(self):

        self.components = {}

    ##################################################

    def update(

        self,

        name,

        status,

    ):

        self.components[name] = status

    ##################################################

    def report(self):

        return self.components

    ##################################################

    def healthy(self):

        return all(

            self.components.values()

        ) if self.components else True