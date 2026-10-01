from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Episodic Memory
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from datetime import datetime


class EpisodicMemory:

    def __init__(self):

        self._episodes = []

    def remember(
        self,
        event: str,
    ):

        self._episodes.append(
            {
                "time": datetime.now(),
                "event": event,
            }
        )

    def latest(self):

        if not self._episodes:
            return None

        return self._episodes[-1]

    def history(self):

        return self._episodes.copy()

    def clear(self):

        self._episodes.clear()