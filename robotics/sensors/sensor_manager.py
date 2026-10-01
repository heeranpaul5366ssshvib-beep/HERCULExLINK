from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Sensor Manager
--------------------------------------------
"""



class SensorManager:

    """
    Robot sensor controller.
    """

    def __init__(self):

        self.sensors = {}

    ##################################################

    def register(

        self,

        name,

        sensor,

    ):

        self.sensors[name] = sensor

    ##################################################

    def read(

        self,

        name,

    ):

        sensor = self.sensors.get(name)

        if sensor is None:

            return None

        return sensor.read()

    ##################################################

    def list(self):

        return list(

            self.sensors.keys()

        )

    ##################################################

    def clear(self):

        self.sensors.clear()