from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Manufacturing Manager
--------------------------------------------
"""



class ManufacturingManager:

    """
    Manufacturing Planner
    """

    def __init__(self):

        self.jobs = []

    ##################################################

    def create_job(

        self,

        name,

        material,

    ):

        self.jobs.append(

            {

                "name": name,

                "material": material,

                "status": "pending",

            }

        )

    ##################################################

    def complete_job(

        self,

        index,

    ):

        if 0 <= index < len(self.jobs):

            self.jobs[index]["status"] = "completed"

    ##################################################

    def list_jobs(self):

        return self.jobs