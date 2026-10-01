from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Automation
--------------------------------------------
"""



class Automation:

    def __init__(

        self,

        abilities,

    ):

        self.abilities = abilities

    ##################################################

    def execute(

        self,

        ability,

        *args,

        **kwargs,

    ):

        return self.abilities.execute(

            ability,

            *args,

            **kwargs,

        )

    ##################################################

    def sequence(

        self,

        tasks,

    ):

        results = []

        for task in tasks:

            results.append(

                self.execute(

                    task["ability"],

                    *task.get("args", []),

                    **task.get("kwargs", {}),

                )

            )

        return results