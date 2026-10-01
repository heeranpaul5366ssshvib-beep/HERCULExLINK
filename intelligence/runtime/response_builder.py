from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Response Builder
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict


logger = logging.getLogger(__name__)


class ResponseBuilder:
    """
    Builds standardized runtime responses.
    """

    def __init__(self):

        self.initialized = False

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Response Builder"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        self.initialized = False

    # --------------------------------------------------

    def build(

        self,

        context: Dict[str, Any],

        result: Any,

    ) -> Dict[str, Any]:

        return {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "status": "success",

            "context": context,

            "result": result,

        }

    # --------------------------------------------------

    def error(

        self,

        message: str,

    ) -> Dict[str, Any]:

        return {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "status": "error",

            "message": message,

        }

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

        }