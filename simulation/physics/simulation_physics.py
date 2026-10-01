from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Simulation Physics
--------------------------------------------
"""



class SimulationPhysics:

    """
    Physics calculations for simulations.
    """

    ##################################################

    def gravity(

        self,

        mass,

        gravity=9.81,

    ):

        return mass * gravity

    ##################################################

    def acceleration(

        self,

        force,

        mass,

    ):

        if mass == 0:

            return 0

        return force / mass

    ##################################################

    def velocity(

        self,

        distance,

        time,

    ):

        if time == 0:

            return 0

        return distance / time