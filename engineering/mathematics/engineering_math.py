from __future__ import annotations
"""
Engineering Mathematics
"""


import math


class EngineeringMath:

    def solve(

        self,

        expression,

    ):

        return eval(

            expression,

            {

                "__builtins__": None,

                "math": math,

            },

            {},

        )