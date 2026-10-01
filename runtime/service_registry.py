from __future__ import annotations
"""
--------------------------------------------
HERCULE Runtime Service Registry
--------------------------------------------
"""



class ServiceRegistry:

    def __init__(self):

        self.services = {}

    ##################################################

    def register(

        self,

        name,

        service,

    ):

        self.services[name] = service

    ##################################################

    def get(

        self,

        name,

    ):

        return self.services.get(name)

    ##################################################

    def exists(

        self,

        name,

    ):

        return name in self.services

    ##################################################

    def all(self):

        return self.services

    ##################################################

    def remove(

        self,

        name,

    ):

        self.services.pop(name, None)

    ##################################################

    def clear(self):

        self.services.clear()