from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Motion Planner
--------------------------------------------
"""



class MotionPlanner:

    """
    Plans robot motion.
    """

    def __init__(self):

        self.plan = []

    ##################################################

    def add_waypoint(

        self,

        position,

    ):

        self.plan.append(position)

    ##################################################

    def clear(self):

        self.plan.clear()

    ##################################################

    def execute(self):

        return self.plan