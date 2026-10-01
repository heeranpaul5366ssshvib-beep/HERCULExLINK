from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Simulation Environment
--------------------------------------------
"""



class Environment:

    """
    Simulation environment.
    """

    def __init__(self):

        self.variables = {}

    ##################################################

    def set(

        self,

        key,

        value,

    ):

        self.variables[key] = value

    ##################################################

    def get(

        self,

        key,

    ):

        return self.variables.get(

            key,

        )

    ##################################################

    def clear(self):

        self.variables.clear()