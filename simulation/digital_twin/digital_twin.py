from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Digital Twin
--------------------------------------------
"""



class DigitalTwin:

    """
    Digital representation of a system.
    """

    def __init__(self):

        self.state = {}

    ##################################################

    def update(

        self,

        key,

        value,

    ):

        self.state[key] = value

    ##################################################

    def snapshot(self):

        return dict(

            self.state,

        )

    ##################################################

    def reset(self):

        self.state.clear()