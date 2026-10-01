from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Confidence Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class ConfidenceLevel(Enum):
    """Confidence classifications."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ConfidenceEngine:
    """
    Calculates confidence for every
    intelligent decision produced by HERCULE.

    Factors

    • Evidence Quality
    • Reasoning Quality
    • Prediction Quality
    • Historical Accuracy
    • Uncertainty
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.history: List[Dict[str, Any]] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing Confidence Engine")

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping Confidence Engine")

        self.history.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        evidence = self.evaluate_evidence(
            pipeline
        )

        reasoning = self.evaluate_reasoning(
            pipeline
        )

        prediction = self.evaluate_prediction(
            pipeline
        )

        history = self.evaluate_history()

        uncertainty = self.evaluate_uncertainty(
            pipeline
        )

        score = self.calculate_confidence(

            evidence,

            reasoning,

            prediction,

            history,

            uncertainty,

        )

        result = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "confidence": score,

            "level": self.classify(score),

            "evidence": evidence,

            "reasoning": reasoning,

            "prediction": prediction,

            "history": history,

            "uncertainty": uncertainty,
        }

        self.history.append(result)

        return result

    # --------------------------------------------------

    def evaluate_evidence(
        self,
        pipeline,
    ) -> float:

        if pipeline.get("concepts"):

            return 0.90

        return 0.40

    # --------------------------------------------------

    def evaluate_reasoning(
        self,
        pipeline,
    ) -> float:

        if pipeline.get("reasoning"):

            return 0.92

        return 0.45

    # --------------------------------------------------

    def evaluate_prediction(
        self,
        pipeline,
    ) -> float:

        if pipeline.get("prediction"):

            return 0.88

        return 0.50

    # --------------------------------------------------

    def evaluate_history(self) -> float:

        return 0.90

    # --------------------------------------------------

    def evaluate_uncertainty(
        self,
        pipeline,
    ) -> float:

        uncertainty = pipeline.get(
            "uncertainty",
            {}
        )

        if isinstance(uncertainty, dict):

            return uncertainty.get(
                "score",
                0.20,
            )

        return 0.20

    # --------------------------------------------------

    def calculate_confidence(

        self,

        evidence,

        reasoning,

        prediction,

        history,

        uncertainty,

    ) -> float:

        score = (

            evidence * 0.25 +

            reasoning * 0.25 +

            prediction * 0.20 +

            history * 0.20 +

            (1.0 - uncertainty) * 0.10

        )

        return round(

            min(

                max(score, 0.0),

                1.0,

            ),

            3,

        )

    # --------------------------------------------------

    def classify(
        self,
        score,
    ) -> str:

        if score < 0.20:

            return ConfidenceLevel.VERY_LOW.value

        if score < 0.40:

            return ConfidenceLevel.LOW.value

        if score < 0.60:

            return ConfidenceLevel.MODERATE.value

        if score < 0.80:

            return ConfidenceLevel.HIGH.value

        return ConfidenceLevel.VERY_HIGH.value

    # --------------------------------------------------

    def recent_history(
        self,
        limit: int = 20,
    ):

        return self.history[-limit:]

    # --------------------------------------------------

    def clear_history(self):

        self.history.clear()

    # --------------------------------------------------

    def statistics(self):

        average = 0.0

        if self.history:

            average = sum(

                item["confidence"]

                for item in self.history

            ) / len(self.history)

        return {

            "initialized": self.initialized,

            "history": len(self.history),

            "average_confidence": round(
                average,
                3,
            ),
        }