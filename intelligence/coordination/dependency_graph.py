from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Dependency Graph
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from collections import defaultdict, deque
from typing import Dict, List, Set


logger = logging.getLogger(__name__)


class DependencyGraph:
    """
    Directed dependency graph used by the
    Intelligence Coordinator.

    Responsibilities

    • Register dependencies
    • Validate modules
    • Detect cycles
    • Produce initialization order
    """

    def __init__(self):

        self.initialized = False

        self.graph: Dict[str, Set[str]] = defaultdict(set)

        self.reverse_graph: Dict[str, Set[str]] = defaultdict(set)

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Dependency Graph"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Dependency Graph"
        )

        self.graph.clear()

        self.reverse_graph.clear()

        self.initialized = False

    # --------------------------------------------------

    def add_module(
        self,
        module: str,
    ):

        self.graph.setdefault(module, set())

        self.reverse_graph.setdefault(
            module,
            set(),
        )

    # --------------------------------------------------

    def add_dependency(
        self,
        module: str,
        dependency: str,
    ):

        self.add_module(module)

        self.add_module(dependency)

        self.graph[module].add(dependency)

        self.reverse_graph[
            dependency
        ].add(module)

    # --------------------------------------------------

    def remove_dependency(
        self,
        module: str,
        dependency: str,
    ):

        self.graph.get(
            module,
            set(),
        ).discard(dependency)

        self.reverse_graph.get(
            dependency,
            set(),
        ).discard(module)

    # --------------------------------------------------

    def dependencies(
        self,
        module: str,
    ) -> List[str]:

        return sorted(

            self.graph.get(

                module,

                set(),

            )

        )

    # --------------------------------------------------

    def dependents(
        self,
        module: str,
    ) -> List[str]:

        return sorted(

            self.reverse_graph.get(

                module,

                set(),

            )

        )

    # --------------------------------------------------

    def has_cycle(self) -> bool:

        return len(
            self.initialization_order()
        ) != len(self.graph)

    # --------------------------------------------------

    def initialization_order(
        self,
    ) -> List[str]:
        """
        Topological sort using Kahn's algorithm.
        """

        indegree = {

            node: len(deps)

            for node, deps

            in self.graph.items()

        }

        queue = deque(

            node

            for node, degree

            in indegree.items()

            if degree == 0

        )

        order: List[str] = []

        reverse = {

            key: value.copy()

            for key, value

            in self.reverse_graph.items()

        }

        while queue:

            node = queue.popleft()

            order.append(node)

            for dependent in reverse.get(
                node,
                set(),
            ):

                indegree[
                    dependent
                ] -= 1

                if (

                    indegree[
                        dependent
                    ]

                    == 0

                ):

                    queue.append(
                        dependent
                    )

        return order

    # --------------------------------------------------

    def validate(self):

        return {

            "cycle_detected":
                self.has_cycle(),

            "modules":
                len(self.graph),

            "order":
                self.initialization_order(),

        }

    # --------------------------------------------------

    def clear(self):

        self.graph.clear()

        self.reverse_graph.clear()

    # --------------------------------------------------

    def statistics(self):

        dependency_count = sum(

            len(value)

            for value

            in self.graph.values()

        )

        return {

            "initialized":
                self.initialized,

            "modules":
                len(self.graph),

            "dependencies":
                dependency_count,

            "cycle_detected":
                self.has_cycle(),

        }