from __future__ import annotations
"""
Material Database
"""



class MaterialManager:

    def __init__(self):

        self.materials = {}

    ##################################################

    def add(

        self,

        name,

        properties,

    ):

        self.materials[name] = properties

    ##################################################

    def get(

        self,

        name,

    ):

        return self.materials.get(name)