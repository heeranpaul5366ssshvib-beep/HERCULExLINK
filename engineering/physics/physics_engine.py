from __future__ import annotations
"""
Physics Engine
"""



class PhysicsEngine:

    def force(

        self,

        mass,

        acceleration,

    ):

        return mass * acceleration

    ##################################################

    def kinetic_energy(

        self,

        mass,

        velocity,

    ):

        return 0.5 * mass * velocity ** 2

    ##################################################

    def momentum(

        self,

        mass,

        velocity,

    ):

        return mass * velocity