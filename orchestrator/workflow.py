from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Workflow
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from datetime import datetime


class Workflow:
    """
    ==========================================
            HERCULE WORKFLOW
    ==========================================

    Executes multi-step AI workflows.
    """

    def __init__(self):

        self.steps = []

        self.history = []

    ##################################################

    def add_step(

        self,

        function,

    ):

        self.steps.append(

            function,

        )

    ##################################################

    def execute(

        self,

        data,

    ):

        result = data

        for step in self.steps:

            result = step(

                result,

            )

        self.history.append(

            {

                "time": datetime.now(),

                "steps": len(

                    self.steps,

                ),

            }

        )

        return result

    ##################################################

    def clear(self):

        self.steps.clear()

    ##################################################

    def executions(self):

        return len(

            self.history,

        )

    ##################################################

    def last_execution(self):

        if not self.history:

            return None

        return self.history[-1]

    ##################################################

    def health(self):

        return {

            "steps": len(

                self.steps,

            ),

            "executions": len(

                self.history,

            ),

        }

    ##################################################
    # FUTURE
    ##################################################

    def save(self):
        pass

    def load(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self):
        pass
