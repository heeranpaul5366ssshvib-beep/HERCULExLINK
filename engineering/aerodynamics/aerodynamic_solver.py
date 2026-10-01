from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Aerodynamic Solver
--------------------------------------------
"""


import math


class AerodynamicSolver:

    """
    Aerodynamic calculations.
    """

    AIR_DENSITY = 1.225

    ##################################################

    def drag_force(

        self,

        drag_coefficient,

        area,

        velocity,

    ):

        return (

            0.5

            * self.AIR_DENSITY

            * drag_coefficient

            * area

            * velocity ** 2

        )

    ##################################################

    def lift_force(

        self,

        lift_coefficient,

        area,

        velocity,

    ):

        return (

            0.5

            * self.AIR_DENSITY

            * lift_coefficient

            * area

            * velocity ** 2

        )

    ##################################################

    def reynolds_number(

        self,

        density,

        velocity,

        length,

        viscosity,

    ):

        return (

            density

            * velocity

            * length

        ) / viscosity