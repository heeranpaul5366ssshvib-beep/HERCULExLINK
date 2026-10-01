from __future__ import annotations
"""
--------------------------------------------
HERCULE Diagnostics
--------------------------------------------
"""



class Diagnostics:

    def run(

        self,

        registry,

    ):

        report = {}

        for name, service in registry.all().items():

            report[name] = service is not None

        return report