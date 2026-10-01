from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Monitoring Manager
--------------------------------------------
"""


import time


class MonitoringManager:

    def __init__(self):

        self.start_time = time.time()

    ##################################################

    def uptime(self):

        return time.time() - self.start_time

    ##################################################

    def snapshot(self):

        return {

            "uptime": self.uptime(),

        }