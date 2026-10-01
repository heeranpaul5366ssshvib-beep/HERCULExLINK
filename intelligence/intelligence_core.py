from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intelligence Core
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class IntelligenceCore:
    """
    Central Intelligence Pipeline.

    Every intelligent subsystem communicates
    through this class.

    Pipeline

        Input
            ↓
        Concepts
            ↓
        Cognition
            ↓
        Inference
            ↓
        Prediction
            ↓
        Optimization
            ↓
        Final Decision
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.manager = None

        self.engines: Dict[str, Any] = {}

        self.running = False

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing Intelligence Core")

        self.manager = self.kernel.get_service(
            "intelligence_manager"
        )

        self.running = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping Intelligence Core")

        self.running = False

        self.engines.clear()

    # --------------------------------------------------

    def register_engine(
        self,
        name: str,
        engine: Any,
    ) -> None:

        logger.info(
            "Registering Intelligence Engine: %s",
            name,
        )

        self.engines[name] = engine

    # --------------------------------------------------

    def unregister_engine(
        self,
        name: str,
    ) -> None:

        if name in self.engines:

            del self.engines[name]

    # --------------------------------------------------

    def get_engine(
        self,
        name: str,
    ) -> Optional[Any]:

        return self.engines.get(name)

    # --------------------------------------------------

    def process(
        self,
        request: Dict[str, Any],
    ) -> Dict[str, Any]:

        result = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "input": request,

            "concepts": None,

            "cognition": None,

            "reasoning": None,

            "prediction": None,

            "optimization": None,

            "response": None,
        }

        #
        # Concept Engine
        #

        engine = self.get_engine("concept")

        if engine:

            result["concepts"] = engine.process(
                request
            )

        #
        # Cognitive Engine
        #

        engine = self.get_engine("cognitive")

        if engine:

            result["cognition"] = engine.process(
                result
            )

        #
        # Inference
        #

        engine = self.get_engine("inference")

        if engine:

            result["reasoning"] = engine.process(
                result
            )

        #
        # Prediction
        #

        engine = self.get_engine("prediction")

        if engine:

            result["prediction"] = engine.process(
                result
            )

        #
        # Optimization
        #

        engine = self.get_engine("optimization")

        if engine:

            result["optimization"] = engine.process(
                result
            )

        result["response"] = self._build_response(
            result
        )

        return result

    # --------------------------------------------------

    def _build_response(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {

            "status": "success",

            "generated": datetime.now(timezone.utc).isoformat(),

            "pipeline": pipeline,
        }

    # --------------------------------------------------

    def available_engines(self):

        return sorted(
            self.engines.keys()
        )

    # --------------------------------------------------

    def publish_event(
        self,
        event: str,
        **kwargs,
    ):

        self.kernel.publish(
            event,
            **kwargs,
        )

    # --------------------------------------------------

    def subscribe(
        self,
        event,
        callback,
    ):

        self.kernel.subscribe(
            event,
            callback,
        )