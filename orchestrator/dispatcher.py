from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Dispatcher
Author: Heeran Paul
License: MIT
--------------------------------------------
"""



class Dispatcher:
    """
    ==========================================
            HERCULE DISPATCHER
    ==========================================

    Determines which subsystem should
    handle an incoming request.
    """

    def __init__(self):

        self.routes = {}

    ##################################################

    def register(

        self,

        name,

        handler,

    ):

        self.routes[name] = handler

    ##################################################

    def unregister(

        self,

        name,

    ):

        self.routes.pop(

            name,

            None,

        )

    ##################################################

    def dispatch(

        self,

        route,

        *args,

        **kwargs,

    ):

        if route not in self.routes:

            raise ValueError(

                f"No handler registered for '{route}'"

            )

        handler = self.routes[route]

        return handler(

            *args,

            **kwargs,

        )

    ##################################################

    def routes_available(self):

        return list(

            self.routes.keys()

        )

    ##################################################

    def clear(self):

        self.routes.clear()

    ##################################################

    def health(self):

        return {

            "registered_routes": len(

                self.routes

            )

        }