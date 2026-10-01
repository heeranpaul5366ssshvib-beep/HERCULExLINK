from __future__ import annotations
"""
Actuator Manager
"""



class ActuatorManager:

    def __init__(self):

        self.actuators = {}

    ##################################################

    def register(

        self,

        name,

        actuator,

    ):

        self.actuators[name] = actuator

    ##################################################

    def move(

        self,

        name,

        value,

    ):

        actuator = self.actuators.get(name)

        if actuator is None:

            return False

        actuator["position"] = value

        return True

    ##################################################

    def state(self):

        return self.actuators