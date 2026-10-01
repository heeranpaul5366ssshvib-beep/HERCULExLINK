from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Hooks
--------------------------------------------
"""



class Hooks:

    """
    Simple event hook system.
    """

    def __init__(self):

        self.events = {}

    ##################################################

    def register(

        self,

        event,

        callback,

    ):

        self.events.setdefault(

            event,

            [],

        ).append(

            callback,

        )

    ##################################################

    def trigger(

        self,

        event,

        *args,

        **kwargs,

    ):

        callbacks = self.events.get(

            event,

            [],

        )

        results = []

        for callback in callbacks:

            results.append(

                callback(

                    *args,

                    **kwargs,

                )

            )

        return results

    ##################################################

    def remove(

        self,

        event,

    ):

        self.events.pop(

            event,

            None,

        )

    ##################################################

    def clear(self):

        self.events.clear()