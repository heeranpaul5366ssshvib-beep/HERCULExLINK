from __future__ import annotations
"""
Localization
"""



class Localization:

    def __init__(self):

        self.position = (0, 0, 0)

    ##################################################

    def update(

        self,

        x,

        y,

        z,

    ):

        self.position = (x, y, z)

    ##################################################

    def current(self):

        return self.position