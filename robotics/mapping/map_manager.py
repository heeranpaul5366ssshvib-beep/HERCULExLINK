from __future__ import annotations
"""
Map Manager
"""



class MapManager:

    def __init__(self):

        self.map = {}

    ##################################################

    def add(

        self,

        name,

        position,

    ):

        self.map[name] = position

    ##################################################

    def get(

        self,

        name,

    ):

        return self.map.get(name)

    ##################################################

    def all(self):

        return self.map