from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Script Manager
--------------------------------------------
"""


from scripts.script import Script


class ScriptManager:

    def __init__(self):

        self.scripts = {}

    ##################################################

    def create(

        self,

        name,

        description="",

    ):

        script = Script(

            name,

            description,

        )

        self.scripts[name] = script

        return script

    ##################################################

    def get(

        self,

        name,

    ):

        return self.scripts.get(name)

    ##################################################

    def execute(

        self,

        name,

        context=None,

    ):

        script = self.get(name)

        if script is None:

            raise ValueError(f"Script '{name}' not found.")

        return script.run(context)

    ##################################################

    def remove(

        self,

        name,

    ):

        self.scripts.pop(name, None)

    ##################################################

    def list(self):

        return list(self.scripts.keys())

    ##################################################

    def clear(self):

        self.scripts.clear()