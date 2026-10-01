from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intuition Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


logger = logging.getLogger(__name__)


class HeuristicType(Enum):
    """Supported intuition heuristics."""

    PATTERN_MATCH = "pattern_match"
    EXPERIENCE = "experience"
    SIMILARITY = "similarity"
    RISK_AVOIDANCE = "risk_avoidance"
    OPPORTUNITY = "opportunity"
    RESOURCE = "resource"
    TEMPORAL = "temporal"


@dataclass
class IntuitionDecision:

    id: str

    heuristic: HeuristicType

    recommendation: str

    confidence: float

    reasoning: List[str] = field(
        default_factory=list
    )

    created: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class IntuitionEngine:
    """
    Produces fast heuristic decisions using
    historical patterns and prior experience.

    Responsibilities

    • Pattern recognition
    • Fast decision proposals
    • Experience-based reasoning
    • Similarity matching
    • Risk-aware recommendations
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.history: List[IntuitionDecision] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Intuition Engine"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Intuition Engine"
        )

        self.history.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        decision = self.generate_decision(
            pipeline
        )

        self.history.append(decision)

        return {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "decision_id": decision.id,

            "recommendation":
                decision.recommendation,

            "heuristic":
                decision.heuristic.value,

            "confidence":
                decision.confidence,
        }

    # --------------------------------------------------

    def generate_decision(
        self,
        pipeline: Dict[str, Any],
    ) -> IntuitionDecision:

        heuristic = self.select_heuristic(
            pipeline
        )

        recommendation = self.make_recommendation(
            heuristic,
            pipeline,
        )

        confidence = self.estimate_confidence(
            pipeline
        )

        return IntuitionDecision(

            id=str(uuid4()),

            heuristic=heuristic,

            recommendation=recommendation,

            confidence=confidence,

            reasoning=[

                "Historical pattern recognized.",

                "Heuristic evaluation completed.",

            ],

        )

    # --------------------------------------------------

    def select_heuristic(
        self,
        pipeline: Dict[str, Any],
    ) -> HeuristicType:

        if pipeline.get("prediction"):

            return HeuristicType.PATTERN_MATCH

        if pipeline.get("uncertainty"):

            return HeuristicType.RISK_AVOIDANCE

        return HeuristicType.EXPERIENCE

    # --------------------------------------------------

    def make_recommendation(

        self,

        heuristic: HeuristicType,

        pipeline: Dict[str, Any],

    ) -> str:

        recommendations = {

            HeuristicType.PATTERN_MATCH:
                "Reuse successful strategy.",

            HeuristicType.EXPERIENCE:
                "Apply historical solution.",

            HeuristicType.SIMILARITY:
                "Adapt similar execution path.",

            HeuristicType.RISK_AVOIDANCE:
                "Reduce uncertainty before acting.",

            HeuristicType.OPPORTUNITY:
                "Prioritize highest-value action.",

            HeuristicType.RESOURCE:
                "Optimize resource allocation.",

            HeuristicType.TEMPORAL:
                "Delay execution for better timing.",
        }

        return recommendations.get(

            heuristic,

            "Continue analysis.",

        )

    # --------------------------------------------------

    def estimate_confidence(
        self,
        pipeline: Dict[str, Any],
    ) -> float:

        confidence = 0.80

        prediction = pipeline.get(
            "prediction",
            {}
        )

        if isinstance(prediction, dict):

            confidence = prediction.get(
                "confidence",
                confidence,
            )

        return round(
            max(0.0, min(confidence, 1.0)),
            3,
        )

    # --------------------------------------------------

    def latest(
        self,
        limit: int = 10,
    ) -> List[IntuitionDecision]:

        return self.history[-limit:]

    # --------------------------------------------------

    def clear_history(self):

        self.history.clear()

    # --------------------------------------------------

    def statistics(self):

        average = 0.0

        if self.history:

            average = sum(

                item.confidence

                for item in self.history

            ) / len(self.history)

        return {

            "initialized": self.initialized,

            "history": len(self.history),

            "heuristics": len(
                HeuristicType
            ),

            "average_confidence": round(
                average,
                3,
            ),
        }