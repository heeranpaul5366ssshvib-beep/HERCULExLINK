from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Intelligence Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from typing import Dict, List, Optional

from intelligence.intelligence_core import IntelligenceCore
from intelligence.cognitive_engine import CognitiveEngine
from intelligence.abstraction_engine import AbstractionEngine
from intelligence.concept_engine import ConceptEngine
from intelligence.inference_engine import InferenceEngine
from intelligence.world_model import WorldModel
from intelligence.prediction_engine import PredictionEngine
from intelligence.adaptation_engine import AdaptationEngine
from intelligence.optimization_engine import OptimizationEngine
from intelligence.uncertainty_engine import UncertaintyEngine
from intelligence.confidence_engine import ConfidenceEngine
from intelligence.meta_learning import MetaLearningEngine
from intelligence.knowledge_synthesis import KnowledgeSynthesisEngine
from intelligence.curiosity_engine import CuriosityEngine
from intelligence.imagination_engine import ImaginationEngine
from intelligence.innovation_engine import InnovationEngine
from intelligence.intuition_engine import IntuitionEngine
from intelligence.intelligence_metrics import IntelligenceMetrics


logger = logging.getLogger(__name__)


class IntelligenceManager:

    """
    Central manager of every
    Intelligence subsystem.
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.modules: Dict[str, object] = {}

        self.initialized = False

        self._build()

    # --------------------------------------------------

    def _build(self):

        self.register(
            "core",
            IntelligenceCore(self.kernel)
        )

        self.register(
            "cognitive_engine",
            CognitiveEngine(self.kernel)
        )

        self.register(
            "abstraction_engine",
            AbstractionEngine(self.kernel)
        )

        self.register(
            "concept_engine",
            ConceptEngine(self.kernel)
        )

        self.register(
            "inference_engine",
            InferenceEngine(self.kernel)
        )

        self.register(
            "world_model",
            WorldModel(self.kernel)
        )

        self.register(
            "prediction_engine",
            PredictionEngine(self.kernel)
        )

        self.register(
            "adaptation_engine",
            AdaptationEngine(self.kernel)
        )

        self.register(
            "optimization_engine",
            OptimizationEngine(self.kernel)
        )

        self.register(
            "uncertainty_engine",
            UncertaintyEngine(self.kernel)
        )

        self.register(
            "confidence_engine",
            ConfidenceEngine(self.kernel)
        )

        self.register(
            "meta_learning",
            MetaLearningEngine(self.kernel)
        )

        self.register(
            "knowledge_synthesis",
            KnowledgeSynthesisEngine(self.kernel)
        )

        self.register(
            "curiosity_engine",
            CuriosityEngine(self.kernel)
        )

        self.register(
            "imagination_engine",
            ImaginationEngine(self.kernel)
        )

        self.register(
            "innovation_engine",
            InnovationEngine(self.kernel)
        )

        self.register(
            "intuition_engine",
            IntuitionEngine(self.kernel)
        )

        self.register(
            "metrics",
            IntelligenceMetrics(self.kernel)
        )

    # --------------------------------------------------

    def register(

        self,

        name: str,

        module,

    ):

        logger.info(
            "Registering %s",
            name,
        )

        self.modules[name] = module

        setattr(
            self,
            name,
            module,
        )

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Intelligence Layer"
        )

        for module in self.modules.values():

            module.initialize()

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Intelligence Layer"
        )

        for module in reversed(

            list(self.modules.values())

        ):

            module.shutdown()

        self.initialized = False

    # --------------------------------------------------

    def get(

        self,

        name: str,

    ) -> Optional[object]:

        return self.modules.get(name)

    # --------------------------------------------------

    def all_modules(self) -> List[object]:

        return list(

            self.modules.values()

        )

    # --------------------------------------------------

    def statistics(self):

        return {

            name: module.statistics()

            for name, module

            in self.modules.items()

        }

    # --------------------------------------------------

    def health(self):

        healthy = 0

        total = len(self.modules)

        for module in self.modules.values():

            if getattr(

                module,

                "initialized",

                False,

            ):

                healthy += 1

        return {

            "initialized":

                self.initialized,

            "healthy_modules":

                healthy,

            "total_modules":

                total,

            "health":

                round(

                    healthy /

                    total,

                    3,

                ) if total else 0.0,

        }