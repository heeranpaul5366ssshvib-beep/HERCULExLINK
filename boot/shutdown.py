from __future__ import annotations
"""
--------------------------------------------
Shutdown Sequence
--------------------------------------------
"""



class Shutdown:

    def execute(

        self,

        runtime,

    ):

        runtime.lifecycle.stop()

        return True