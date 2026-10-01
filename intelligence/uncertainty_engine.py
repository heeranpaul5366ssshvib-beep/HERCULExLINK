from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Uncertainty Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class UncertaintyLevel(Enum):
    """Uncertainty classification."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class UncertaintyEngine:
    """
    Estimates uncertainty throughout the
    intelligence pipeline.

    Responsibilities
    ----------------
    • Detect missing information
    • Measure ambiguity
    • Detect conflicting evidence
    • Estimate uncertainty scores
    • Recommend additional reasoning
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.history: List[Dict[str, Any]] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing Uncertainty Engine")

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping Uncertainty Engine")

        self.history.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        result = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "missing_information":
                self.detect_missing_information(
                    pipeline
                ),

            "ambiguity":
                self.measure_ambiguity(
                    pipeline
                ),

            "conflicts":
                self.detect_conflicts(
                    pipeline
                ),

            "score":
                self.calculate_uncertainty(
                    pipeline
                ),

            "level":
                self.classify_uncertainty(
                    pipeline
                ),

            "recommendations":
                self.generate_recommendations(
                    pipeline
                ),
        }

        self.history.append(result)

        return result

    # --------------------------------------------------

    def detect_missing_information(
        self,
        pipeline: Dict[str, Any],
    ) -> List[str]:

        missing = []

        required = [

            "input",

            "concepts",

            "reasoning",

            "prediction",

        ]

        for item in required:

            if item not in pipeline:

                missing.append(item)

        return missing

    # --------------------------------------------------

    def measure_ambiguity(
        self,
        pipeline: Dict[str, Any],
    ) -> float:

        score = 0.0

        if not pipeline.get("concepts"):

            score += 0.30

        if not pipeline.get("reasoning"):

            score += 0.30

        if not pipeline.get("prediction"):

            score += 0.20

        return min(score, 1.0)

    # --------------------------------------------------

    def detect_conflicts(
        self,
        pipeline: Dict[str, Any],
    ) -> List[str]:

        conflicts = []

        prediction = pipeline.get(
            "prediction",
            {}
        )

        reasoning = pipeline.get(
            "reasoning",
            {}
        )

        if prediction and reasoning:

            if prediction.get("confidence", 1.0) < 0.30:

                conflicts.append(

                    "Prediction confidence is low."

                )

        return conflicts

    # --------------------------------------------------

    def calculate_uncertainty(
        self,
        pipeline: Dict[str, Any],
    ) -> float:

        ambiguity = self.measure_ambiguity(
            pipeline
        )

        missing = len(

            self.detect_missing_information(
                pipeline
            )

        )

        score = ambiguity + (missing * 0.05)

        return min(score, 1.0)

    # --------------------------------------------------

    def classify_uncertainty(
        self,
        pipeline: Dict[str, Any],
    ) -> str:

        score = self.calculate_uncertainty(
            pipeline
        )

        if score < 0.10:

            return UncertaintyLevel.VERY_LOW.value

        if score < 0.30:

            return UncertaintyLevel.LOW.value

        if score < 0.60:

            return UncertaintyLevel.MODERATE.value

        if score < 0.80:

            return UncertaintyLevel.HIGH.value

        return UncertaintyLevel.VERY_HIGH.value

    # --------------------------------------------------

    def generate_recommendations(
        self,
        pipeline: Dict[str, Any],
    ) -> List[str]:

        recommendations = []

        score = self.calculate_uncertainty(
            pipeline
        )

        if score > 0.50:

            recommendations.append(

                "Collect additional evidence."

            )

            recommendations.append(

                "Request more information."

            )

            recommendations.append(

                "Increase reasoning depth."

            )

        return recommendations

    # --------------------------------------------------

    def recent_history(
        self,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:

        return self.history[-limit:]

    # --------------------------------------------------

    def clear_history(self):

        self.history.clear()

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "history": len(self.history),

            "supported_levels": len(
                UncertaintyLevel
            ),
        }