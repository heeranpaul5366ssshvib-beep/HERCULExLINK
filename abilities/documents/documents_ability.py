from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Document Ability
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from abilities.base_ability import BaseAbility


class DocumentAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "documents",
            "Document processing"
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

            "document": task,

        }