from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Goal Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class GoalManager:

    def __init__(self):

        self._goals = {}

    def add(

        self,

        name: str,

        description: str,

    ):

        self._goals[name] = {

            "description": description,

            "completed": False,

        }

    def complete(

        self,

        name: str,

    ):

        if name in self._goals:

            self._goals[name]["completed"] = True

    def remove(

        self,

        name: str,

    ):

        self._goals.pop(name, None)

    def get(

        self,

        name: str,

    ):

        return self._goals.get(name)

    def active(self):

        return {

            k: v

            for k, v in self._goals.items()

            if not v["completed"]

        }

    def completed(self):

        return {

            k: v

            for k, v in self._goals.items()

            if v["completed"]

        }

    def clear(self):

        self._goals.clear()