from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Ability Registry
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class AbilityRegistry:

    def __init__(self):

        self._abilities = {}

    ##################################################

    def register(

        self,

        ability,

    ):

        self._abilities[ability.name] = ability

    ##################################################

    def unregister(

        self,

        name,

    ):

        self._abilities.pop(name, None)

    ##################################################

    def get(

        self,

        name,

    ):

        return self._abilities.get(name)

    ##################################################

    def all(self):

        return self._abilities

    ##################################################

    def names(self):

        return list(self._abilities.keys())