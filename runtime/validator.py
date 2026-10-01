from __future__ import annotations
"""
--------------------------------------------
Runtime Validator
--------------------------------------------
"""



class RuntimeValidator:

    REQUIRED = [

        "kernel",

        "brain",

        "memory",

        "knowledge",

        "models",

        "abilities",

        "orchestrator",

        "system",

    ]

    ##################################################

    def validate(

        self,

        registry,

    ):

        missing = []

        for service in self.REQUIRED:

            if not registry.exists(service):

                missing.append(service)

        return {

            "valid": len(missing) == 0,

            "missing": missing,

        }