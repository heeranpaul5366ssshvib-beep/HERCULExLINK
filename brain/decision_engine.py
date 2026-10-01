from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Decision Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class DecisionEngine:

    """
    Executive decision engine.
    """

    ##################################################

    def decide(

        self,

        options,

    ):

        if not options:

            return None

        return options[0]

    ##################################################

    def approve(

        self,

        decision,

    ):

        return True

    ##################################################

    def reject(

        self,

        decision,

    ):

        return False
