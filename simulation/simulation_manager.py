from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Simulation Manager
--------------------------------------------
"""



class SimulationManager:

    """
    Master Simulation Controller
    """

    def __init__(self):

        self.modules = {}

        self.running = False

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

    def start(self):

        self.running = True

    ##################################################

    def stop(self):

        self.running = False

    ##################################################

    def execute(

        self,

        module,

        *args,

        **kwargs,

    ):

        simulator = self.modules.get(module)

        if simulator is None:

            raise ValueError(

                f"{module} not registered."

            )

        return simulator.execute(

            *args,

            **kwargs,

        )

    ##################################################

    def status(self):

        return {

            "running": self.running,

            "modules": list(self.modules.keys())

        }