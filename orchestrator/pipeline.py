from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Pipeline
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class Pipeline:
    """
    ==========================================
            HERCULE PIPELINE
    ==========================================

    Executes a sequence of processing stages.

    Future:
    • Dynamic Pipelines
    • Conditional Branches
    • Parallel Pipelines
    • Async Execution
    """

    def __init__(self):

        self.stages = []

    ##################################################

    def add_stage(

        self,

        stage,

    ):

        self.stages.append(stage)

    ##################################################

    def remove_stage(

        self,

        stage,

    ):

        if stage in self.stages:

            self.stages.remove(stage)

    ##################################################

    def execute(

        self,

        data,

    ):

        result = data

        for stage in self.stages:

            result = stage(result)

        return result

    ##################################################

    def clear(self):

        self.stages.clear()

    ##################################################

    def count(self):

        return len(

            self.stages

        )

    ##################################################

    def health(self):

        return {

            "stages": len(

                self.stages

            )

        }

    ##################################################

    def reset(self):

        self.clear()
