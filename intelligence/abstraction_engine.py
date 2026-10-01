from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Abstraction Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set


logger = logging.getLogger(__name__)


class AbstractionEngine:
    """
    Converts concrete information into higher-level
    abstract knowledge.

    Example

    Apple
    Orange
    Banana

            ↓

    Fruit

            ↓

    Food

            ↓

    Nutrition
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.concepts: Dict[str, Set[str]] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing Abstraction Engine")

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping Abstraction Engine")

        self.concepts.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        source = pipeline.get("input", {})

        abstraction = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "entities": self.extract_entities(source),

            "relationships": self.extract_relationships(source),

            "categories": self.build_categories(source),

            "abstractions": self.generate_abstractions(source),
        }

        return abstraction

    # --------------------------------------------------

    def extract_entities(
        self,
        data: Any,
    ) -> List[str]:

        entities = []

        if isinstance(data, dict):

            entities.extend(data.keys())

        elif isinstance(data, list):

            entities.extend(
                str(item)
                for item in data
            )

        elif isinstance(data, str):

            entities.extend(
                data.split()
            )

        return entities

    # --------------------------------------------------

    def extract_relationships(
        self,
        data: Any,
    ) -> List[Dict[str, str]]:

        relationships = []

        if isinstance(data, dict):

            for key, value in data.items():

                relationships.append({

                    "source": key,

                    "relation": "contains",

                    "target": str(value)

                })

        return relationships

    # --------------------------------------------------

    def build_categories(
        self,
        data: Any,
    ) -> List[str]:

        categories = []

        if isinstance(data, dict):

            categories.append("structured")

        elif isinstance(data, list):

            categories.append("collection")

        elif isinstance(data, str):

            categories.append("language")

        else:

            categories.append("generic")

        return categories

    # --------------------------------------------------

    def generate_abstractions(
        self,
        data: Any,
    ) -> List[str]:

        abstractions = []

        if isinstance(data, dict):

            abstractions.append("knowledge")

        if isinstance(data, list):

            abstractions.append("sequence")

        if isinstance(data, str):

            abstractions.append("communication")

        if not abstractions:

            abstractions.append("general_information")

        return abstractions

    # --------------------------------------------------

    def register_concept(
        self,
        category: str,
        concept: str,
    ):

        self.concepts.setdefault(
            category,
            set(),
        ).add(concept)

    # --------------------------------------------------

    def get_concepts(
        self,
        category: str,
    ) -> List[str]:

        return sorted(

            self.concepts.get(

                category,

                set(),

            )

        )

    # --------------------------------------------------

    def statistics(self):

        return {

            "categories": len(self.concepts),

            "concepts": sum(

                len(v)

                for v in self.concepts.values()

            ),

            "initialized": self.initialized,
        }