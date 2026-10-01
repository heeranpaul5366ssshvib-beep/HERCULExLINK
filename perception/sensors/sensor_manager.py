from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Sensor Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class SensorManager:

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

    def unregister(

        self,

        name,

    ):

        self.sensors.pop(name, None)

    ##################################################

    def read(

        self,

        name,

    ):

        sensor = self.sensors.get(name)

        if sensor is None:

            return None

        if hasattr(sensor, "read"):

            return sensor.read()

        return None

    ##################################################

    def read_all(self):

        data = {}

        for name in self.sensors:

            data[name] = self.read(name)

        return data

    ##################################################

    def names(self):

        return list(self.sensors.keys())

    ##################################################

    def clear(self):

        self.sensors.clear()