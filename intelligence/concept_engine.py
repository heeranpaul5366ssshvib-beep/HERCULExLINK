from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Concept Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


logger = logging.getLogger(__name__)


class ConceptEngine:
    """
    Builds and maintains HERCULE's semantic concept graph.

    Responsibilities
    ----------------
    • Concept creation
    • Hierarchical relationships
    • Association mapping
    • Similarity lookup
    • Generalization
    • Specialization
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.graph: Dict[str, Dict[str, Set[str]]] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing Concept Engine")

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping Concept Engine")

        self.graph.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        abstractions = pipeline.get(
            "abstractions",
            {}
        )

        concepts = []

        for concept in abstractions.get(
            "abstractions",
            []
        ):

            self.add_concept(concept)

            concepts.append(concept)

        return {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "concepts": concepts,

            "graph_size": len(self.graph),
        }

    # --------------------------------------------------

    def add_concept(
        self,
        name: str,
    ):

        if name not in self.graph:

            self.graph[name] = {

                "parents": set(),

                "children": set(),

                "related": set(),
            }

    # --------------------------------------------------

    def link_parent(
        self,
        child: str,
        parent: str,
    ):

        self.add_concept(child)

        self.add_concept(parent)

        self.graph[child]["parents"].add(parent)

        self.graph[parent]["children"].add(child)

    # --------------------------------------------------

    def link_related(
        self,
        first: str,
        second: str,
    ):

        self.add_concept(first)

        self.add_concept(second)

        self.graph[first]["related"].add(second)

        self.graph[second]["related"].add(first)

    # --------------------------------------------------

    def parents(
        self,
        concept: str,
    ) -> List[str]:

        if concept not in self.graph:

            return []

        return sorted(
            self.graph[concept]["parents"]
        )

    # --------------------------------------------------

    def children(
        self,
        concept: str,
    ) -> List[str]:

        if concept not in self.graph:

            return []

        return sorted(
            self.graph[concept]["children"]
        )

    # --------------------------------------------------

    def related(
        self,
        concept: str,
    ) -> List[str]:

        if concept not in self.graph:

            return []

        return sorted(
            self.graph[concept]["related"]
        )

    # --------------------------------------------------

    def exists(
        self,
        concept: str,
    ) -> bool:

        return concept in self.graph

    # --------------------------------------------------

    def remove(
        self,
        concept: str,
    ):

        if concept not in self.graph:

            return

        del self.graph[concept]

    # --------------------------------------------------

    def merge(
        self,
        first: str,
        second: str,
        merged_name: str,
    ):

        self.add_concept(merged_name)

        for node in (first, second):

            if node not in self.graph:

                continue

            self.graph[merged_name]["parents"].update(
                self.graph[node]["parents"]
            )

            self.graph[merged_name]["children"].update(
                self.graph[node]["children"]
            )

            self.graph[merged_name]["related"].update(
                self.graph[node]["related"]
            )

    # --------------------------------------------------

    def statistics(self):

        edges = 0

        for node in self.graph.values():

            edges += len(node["parents"])

            edges += len(node["children"])

            edges += len(node["related"])

        return {

            "concepts": len(self.graph),

            "relationships": edges,

            "initialized": self.initialized,
        }