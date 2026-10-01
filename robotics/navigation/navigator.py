from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Navigator
--------------------------------------------
"""



class Navigator:

    """
    Robot navigation.
    """

    def __init__(self):

        self.destination = None

    ##################################################

    def set_destination(

        self,

        destination,

    ):

        self.destination = destination

    ##################################################

    def current_destination(self):

        return self.destination

    ##################################################

    def navigate(self):

        if self.destination is None:

            return {

                "status": "No destination"

            }

        return {

            "status": "Navigating",

            "destination": self.destination,

        }