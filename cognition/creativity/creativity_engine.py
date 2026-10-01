from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Creativity Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import random


class CreativityEngine:

    def brainstorm(
        self,
        topic: str,
        count: int = 10,
    ):

        return [

            f"{topic} Idea {i}"

            for i in range(1, count + 1)

        ]

    def random_choice(
        self,
        ideas: list[str],
    ):

        if not ideas:
            return None

        return random.choice(ideas)