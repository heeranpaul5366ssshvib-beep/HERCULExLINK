from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Feedback Loop
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class FeedbackLoop:
    """
    Records execution feedback so future
    decisions can improve.
    """

    def __init__(self):

        self.initialized = False

        self.feedback: List[Dict[str, Any]] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Feedback Loop"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        self.feedback.clear()

        self.initialized = False

    # --------------------------------------------------

    def record(

        self,

        request: Any,

        response: Any,

        success: bool,

    ):

        self.feedback.append(

            {

                "timestamp": datetime.now(timezone.utc).isoformat(),

                "request": request,

                "response": response,

                "success": success,

            }

        )

    # --------------------------------------------------

    def success_rate(self) -> float:

        if not self.feedback:

            return 0.0

        successful = sum(

            1

            for item in self.feedback

            if item["success"]

        )

        return round(

            successful /

            len(self.feedback),

            3,

        )

    # --------------------------------------------------

    def latest(

        self,

        limit: int = 10,

    ) -> List[Dict[str, Any]]:

        return self.feedback[-limit:]

    # --------------------------------------------------

    def clear(self):

        self.feedback.clear()

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "feedback_entries": len(

                self.feedback

            ),

            "success_rate": self.success_rate(),

        }