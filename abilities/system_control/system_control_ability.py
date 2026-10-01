from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: System Control Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abilities.base_ability import BaseAbility


class SystemControlAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "system_control",
            "Operating system control"
        )

    ##################################################

    def execute(
        self,
        task,
        context=None,
        **kwargs,
    ):

        return {

            "status": "pending",

            "command": task,

        }