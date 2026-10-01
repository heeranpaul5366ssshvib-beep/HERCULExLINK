from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Engineering Manager
--------------------------------------------
"""



class EngineeringManager:

    """
    Master Engineering Controller
    """

    def __init__(self):

        self.modules = {}

    ##################################################

    def register(

        self,

        name,

        module,

    ):

        self.modules[name] = module

    ##################################################

    def get(

        self,

        name,

    ):

        return self.modules.get(name)

    ##################################################

    def execute(

        self,

        name,

        *args,

        **kwargs,

    ):

        module = self.get(name)

        if module is None:

            raise ValueError(

                f"{name} not registered."

            )

        return module.execute(

            *args,

            **kwargs,

        )

    ##################################################

    def modules_list(self):

        return list(

            self.modules.keys()

        )

    ##################################################

    def clear(self):

        self.modules.clear()