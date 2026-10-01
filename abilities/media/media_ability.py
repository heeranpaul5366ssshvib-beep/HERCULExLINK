from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Media Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abilities.base_ability import BaseAbility


class MediaAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "media",
            "Media processing"
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

            "media": task,

        }