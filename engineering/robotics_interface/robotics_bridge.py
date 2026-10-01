from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Robotics Bridge
--------------------------------------------
"""



class RoboticsBridge:

    """
    Connects Engineering with Robotics.
    """

    def __init__(

        self,

        robotics_manager=None,

    ):

        self.robotics = robotics_manager

    ##################################################

    def connect(

        self,

        robotics_manager,

    ):

        self.robotics = robotics_manager

    ##################################################

    def send(

        self,

        command,

        *args,

        **kwargs,

    ):

        if self.robotics is None:

            raise RuntimeError(

                "Robotics manager not connected."

            )

        return self.robotics.execute(

            command,

            *args,

            **kwargs,

        )