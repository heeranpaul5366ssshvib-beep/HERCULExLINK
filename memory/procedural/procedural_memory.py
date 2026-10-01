from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Procedural Memory
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any


class ProceduralMemory:

    def __init__(self):

        self._skills: dict[str, Any] = {}

    def learn(
        self,
        skill: str,
        procedure: Any,
    ):

        self._skills[skill] = procedure

    def execute(
        self,
        skill: str,
    ):

        return self._skills.get(skill)

    def forget(
        self,
        skill: str,
    ):

        self._skills.pop(skill, None)

    def skills(self):

        return list(self._skills.keys())

    def clear(self):

        self._skills.clear()