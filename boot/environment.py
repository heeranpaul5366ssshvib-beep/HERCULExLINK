from __future__ import annotations
"""
--------------------------------------------
HERCULE Runtime Environment
--------------------------------------------
"""


import os
import platform
import sys


class Environment:

    def __init__(self):

        self.info = {

            "platform": platform.system(),

            "platform_version": platform.version(),

            "python_version": sys.version,

            "cpu": platform.processor(),

            "cwd": os.getcwd(),

        }

    ##################################################

    def get(self):

        return self.info

    ##################################################

    def update(

        self,

        key,

        value,

    ):

        self.info[key] = value