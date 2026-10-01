from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intelligence
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class Intelligence:

    """
    High-level intelligence metrics.
    """

    def __init__(self):

        self.experience = 0

        self.tasks_completed = 0

        self.success_rate = 1.0

    ##################################################

    def learn(self):

        self.experience += 1

    ##################################################

    def complete_task(self):

        self.tasks_completed += 1

    ##################################################

    def intelligence_score(self):

        return {

            "experience": self.experience,

            "tasks": self.tasks_completed,

            "success_rate": self.success_rate,

        }

    ##################################################

    def reset(self):

        self.experience = 0

        self.tasks_completed = 0

        self.success_rate = 1.0