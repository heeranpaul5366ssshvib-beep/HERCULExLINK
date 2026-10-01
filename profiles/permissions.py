from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Permissions
--------------------------------------------
"""



class Permissions:

    def __init__(self):

        self.permissions = {}

    ##################################################

    def allow(

        self,

        name,

    ):

        self.permissions[name] = True

    ##################################################

    def deny(

        self,

        name,

    ):

        self.permissions[name] = False

    ##################################################

    def check(

        self,

        name,

    ):

        return self.permissions.get(

            name,

            False,

        )

    ##################################################

    def clear(self):

        self.permissions.clear()