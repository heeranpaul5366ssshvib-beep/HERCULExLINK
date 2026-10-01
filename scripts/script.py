from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Script
--------------------------------------------
"""


from datetime import datetime


class Script:

    def __init__(

        self,

        name,

        description="",

        actions=None,

    ):

        self.name = name

        self.description = description

        self.actions = actions or []

        self.created = datetime.now()

    ##################################################

    def add_action(

        self,

        action,

    ):

        self.actions.append(action)

    ##################################################

    def remove_action(

        self,

        index,

    ):

        if 0 <= index < len(self.actions):

            self.actions.pop(index)

    ##################################################

    def run(

        self,

        context=None,

    ):

        results = []

        for action in self.actions:

            if callable(action):

                results.append(action(context))

            else:

                results.append(action)

        return results