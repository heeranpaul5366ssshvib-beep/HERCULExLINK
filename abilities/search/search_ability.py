from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Search Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abilities.base_ability import BaseAbility


class SearchAbility(BaseAbility):

    def __init__(self):

        super().__init__(

            "search",

            "Search internal knowledge",

        )

    ##################################################

    def execute(

        self,

        query,

        knowledge_manager,

    ):

        return knowledge_manager.retrieve(

            query,

        )