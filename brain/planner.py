from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Planner
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class Planner:

    """
    Executive Planner

    Uses Cognition Planner
    to generate execution plans.
    """

    def __init__(self):

        self.current_plan = []

    ##################################################

    def create(

        self,

        goal,

    ):

        self.current_plan = [

            {

                "step": 1,

                "goal": goal,

                "status": "pending",

            }

        ]

        return self.current_plan

    ##################################################

    def add_step(

        self,

        description,

    ):

        self.current_plan.append(

            {

                "step": len(self.current_plan) + 1,

                "goal": description,

                "status": "pending",

            }

        )

    ##################################################

    def complete_step(

        self,

        step,

    ):

        if 0 < step <= len(self.current_plan):

            self.current_plan[step - 1]["status"] = "completed"

    ##################################################

    def reset(self):

        self.current_plan.clear()
