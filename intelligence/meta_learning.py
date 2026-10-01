from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Meta Learning
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class LearningStrategy(Enum):
    """
    Available learning strategies.
    """

    REASONING = "reasoning"

    MEMORY = "memory"

    PREDICTION = "prediction"

    PLANNING = "planning"

    KNOWLEDGE = "knowledge"

    OPTIMIZATION = "optimization"

    MODEL_SELECTION = "model_selection"


class MetaLearningEngine:
    """
    Learns how HERCULE learns.

    Responsibilities

    • Evaluate learning strategies
    • Improve reasoning
    • Improve planning
    • Improve memory retrieval
    • Improve model selection
    • Improve prediction quality
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.history: List[Dict[str, Any]] = []

        self.strategy_scores = {

            strategy.value: 1.0

            for strategy in LearningStrategy

        }

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Meta Learning Engine"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Meta Learning Engine"
        )

        self.history.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        evaluation = self.evaluate_learning(
            pipeline
        )

        best = self.best_strategy()

        result = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "evaluation": evaluation,

            "best_strategy": best,

            "strategy_scores": dict(
                self.strategy_scores
            ),

        }

        self.history.append(result)

        return result

    # --------------------------------------------------

    def evaluate_learning(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, float]:

        updates = {}

        for strategy in LearningStrategy:

            name = strategy.value

            current = self.strategy_scores[name]

            improved = min(
                current + 0.01,
                2.0,
            )

            self.strategy_scores[name] = improved

            updates[name] = improved

        return updates

    # --------------------------------------------------

    def reward(
        self,
        strategy: str,
        amount: float = 0.05,
    ):

        if strategy not in self.strategy_scores:

            return

        self.strategy_scores[strategy] = min(

            self.strategy_scores[strategy] + amount,

            2.0,

        )

    # --------------------------------------------------

    def penalize(
        self,
        strategy: str,
        amount: float = 0.05,
    ):

        if strategy not in self.strategy_scores:

            return

        self.strategy_scores[strategy] = max(

            self.strategy_scores[strategy] - amount,

            0.0,

        )

    # --------------------------------------------------

    def best_strategy(self) -> Optional[str]:

        if not self.strategy_scores:

            return None

        return max(

            self.strategy_scores,

            key=self.strategy_scores.get,

        )

    # --------------------------------------------------

    def strategy_score(
        self,
        strategy: str,
    ) -> float:

        return self.strategy_scores.get(

            strategy,

            0.0,

        )

    # --------------------------------------------------

    def reset(self):

        for strategy in LearningStrategy:

            self.strategy_scores[
                strategy.value
            ] = 1.0

    # --------------------------------------------------

    def statistics(self):

        average = sum(

            self.strategy_scores.values()

        ) / len(self.strategy_scores)

        return {

            "initialized": self.initialized,

            "history": len(self.history),

            "strategies": len(
                self.strategy_scores
            ),

            "average_score": round(
                average,
                3,
            ),

            "best_strategy": self.best_strategy(),

        }