from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Scheduler
--------------------------------------------
"""


import time


class Scheduler:

    def __init__(self):

        self.jobs = []

    ##################################################

    def add(

        self,

        interval,

        callback,

    ):

        self.jobs.append(

            {

                "interval": interval,

                "callback": callback,

                "last": 0,

            }

        )

    ##################################################

    def run_once(self):

        now = time.time()

        for job in self.jobs:

            if now - job["last"] >= job["interval"]:

                job["callback"]()

                job["last"] = now

    ##################################################

    def clear(self):

        self.jobs.clear()