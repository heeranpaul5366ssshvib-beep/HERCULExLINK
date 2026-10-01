from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
CAD Manager
--------------------------------------------
"""


from pathlib import Path


class CADManager:

    """
    CAD Project Manager
    """

    def __init__(self):

        self.projects = {}

    ##################################################

    def create_project(

        self,

        name,

        directory,

    ):

        path = Path(directory)

        path.mkdir(

            parents=True,

            exist_ok=True,

        )

        self.projects[name] = path

        return path

    ##################################################

    def open_project(

        self,

        name,

    ):

        return self.projects.get(

            name,

        )

    ##################################################

    def list_projects(self):

        return list(

            self.projects.keys()

        )