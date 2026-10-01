from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Electronics Manager
--------------------------------------------
"""



class ElectronicsManager:

    """
    Electronics calculations.
    """

    ##################################################

    def ohms_law(

        self,

        voltage=None,

        current=None,

        resistance=None,

    ):

        if voltage is None:

            return current * resistance

        if current is None:

            return voltage / resistance

        if resistance is None:

            return voltage / current

    ##################################################

    def power(

        self,

        voltage,

        current,

    ):

        return voltage * current