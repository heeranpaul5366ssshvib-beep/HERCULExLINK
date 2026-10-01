from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Executor
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from datetime import datetime


class Executor:
    """
    ==========================================
            HERCULE EXECUTOR
    ==========================================

    Executes tasks after they have been
    dispatched by the Dispatcher.
    """

    def __init__(self):

        self.executed_tasks = []

        self.failed_tasks = []

    ##################################################

    def execute(

        self,

        task,

        *args,

        **kwargs,

    ):

        try:

            result = task(

                *args,

                **kwargs,

            )

            self.executed_tasks.append(

                {

                    "time": datetime.now(),

                    "task": task.__name__,

                    "status": "SUCCESS",

                }

            )

            return result

        except Exception as error:

            self.failed_tasks.append(

                {

                    "time": datetime.now(),

                    "task": task.__name__,

                    "status": "FAILED",

                    "error": str(error),

                }

            )

            raise

    ##################################################

    def history(self):

        return self.executed_tasks

    ##################################################

    def failures(self):

        return self.failed_tasks

    ##################################################

    def total_tasks(self):

        return len(

            self.executed_tasks

        )

    ##################################################

    def total_failures(self):

        return len(

            self.failed_tasks

        )

    ##################################################

    def clear(self):

        self.executed_tasks.clear()

        self.failed_tasks.clear()

    ##################################################

    def health(self):

        return {

            "executed": len(

                self.executed_tasks

            ),

            "failed": len(

                self.failed_tasks

            ),

        }

    ##################################################
    # FUTURE FEATURES
    ##################################################

    def execute_parallel(self):
        """
        Future:
        Parallel task execution.
        """
        pass

    ##################################################

    def execute_async(self):
        """
        Future:
        Async execution.
        """
        pass

    ##################################################

    def cancel_task(self):
        """
        Future:
        Cancel running task.
        """
        pass

    ##################################################

    def pause_task(self):
        """
        Future:
        Pause execution.
        """
        pass

    ##################################################

    def resume_task(self):
        """
        Future:
        Resume execution.
        """
        pass

    ##################################################

    def priority_execution(self):
        """
        Future:
        Priority scheduling.
        """
        pass

    ##################################################

    def distributed_execution(self):
        """
        Future:
        Multi-device execution.
        """
        pass