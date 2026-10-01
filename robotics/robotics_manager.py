from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Robotics Manager
--------------------------------------------
"""



class RoboticsManager:

    """
    Master Robotics Controller
    """

    def __init__(self):

        self.modules = {}

        self.connected = False

    ##################################################

    def connect(self):

        self.connected = True

    ##################################################

    def disconnect(self):

        self.connected = False

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

        module,

        *args,

        **kwargs,

    ):

        handler = self.modules.get(module)

        if handler is None:

            raise ValueError(f"{module} not registered.")

        return handler.execute(

            *args,

            **kwargs,

        )

    ##################################################

    def status(self):

        return {

            "connected": self.connected,

            "modules": list(self.modules.keys())

        }