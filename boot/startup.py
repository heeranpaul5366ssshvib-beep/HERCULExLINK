from __future__ import annotations
"""
--------------------------------------------
Startup Sequence
--------------------------------------------
"""



class Startup:

    def execute(

        self,

        runtime,

    ):

        runtime.initialize()

        runtime.lifecycle.start()

        return True                      