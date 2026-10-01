from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Calculator Plugin
--------------------------------------------
"""


from plugin_sdk.plugin import Plugin


class CalculatorPlugin(Plugin):

    name = "calculator"

    version = "1.0.0"

    author = "HERCULE"

    ##################################################

    def execute(

        self,

        expression,

    ):

        try:

            return eval(

                expression,

                {

                    "__builtins__": {}

                },

                {},

            )

        except Exception as error:

            return str(error)