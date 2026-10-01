from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intelligence Pipeline
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from collections import OrderedDict
from typing import Any, Callable, Dict, List


logger = logging.getLogger(__name__)


class IntelligencePipeline:
    """
    Manages the execution order of
    intelligence runtime stages.
    """

    def __init__(self):

        self._stages: "OrderedDict[str, Callable]" = OrderedDict()

    # --------------------------------------------------

    def register_stage(
        self,
        name: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:

        if name in self._stages:

            logger.warning(
                "Replacing pipeline stage '%s'",
                name,
            )

        self._stages[name] = handler

    # --------------------------------------------------

    def remove_stage(
        self,
        name: str,
    ) -> None:

        self._stages.pop(name, None)

    # --------------------------------------------------

    def execute(
        self,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:

        pipeline = dict(context)

        for name, stage in self._stages.items():

            logger.debug(
                "Executing stage: %s",
                name,
            )

            result = stage(pipeline)

            if isinstance(result, dict):

                pipeline[name] = result

        return pipeline

    # --------------------------------------------------

    def stage_names(self) -> List[str]:

        return list(self._stages.keys())

    # --------------------------------------------------

    def clear(self):

        self._stages.clear()

    # --------------------------------------------------

    def statistics(self):

        return {

            "registered_stages": len(self._stages),

            "stages": self.stage_names(),

        }