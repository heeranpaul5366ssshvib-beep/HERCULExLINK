from __future__ import annotations
"""
--------------------------------------------
Runtime Dependency Graph
--------------------------------------------
"""



class DependencyGraph:

    def __init__(self):

        self.graph = {}

    ##################################################

    def add(

        self,

        service,

        depends_on=None,

    ):

        self.graph[service] = depends_on or []

    ##################################################

    def dependencies(

        self,

        service,

    ):

        return self.graph.get(

            service,

            [],

        )

    ##################################################

    def services(self):

        return list(

            self.graph.keys()

        )