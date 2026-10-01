from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Execution Graph
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Set


logger = logging.getLogger(__name__)


@dataclass
class ExecutionNode:
    """
    Represents one executable module
    within the coordinator.
    """

    name: str

    dependencies: Set[str] = field(
        default_factory=set
    )

    dependents: Set[str] = field(
        default_factory=set
    )

    completed: bool = False

    started: datetime | None = None

    finished: datetime | None = None


class ExecutionGraph:
    """
    Converts dependency information into an
    executable runtime graph.

    Responsibilities

    • Build execution graph
    • Determine execution order
    • Identify parallel stages
    • Track execution progress
    """

    def __init__(self):

        self.initialized = False

        self.nodes: Dict[str, ExecutionNode] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Execution Graph"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Execution Graph"
        )

        self.nodes.clear()

        self.initialized = False

    # --------------------------------------------------

    def add_node(
        self,
        name: str,
    ):

        self.nodes.setdefault(
            name,
            ExecutionNode(name=name),
        )

    # --------------------------------------------------

    def add_dependency(
        self,
        module: str,
        dependency: str,
    ):

        self.add_node(module)

        self.add_node(dependency)

        self.nodes[module].dependencies.add(
            dependency
        )

        self.nodes[dependency].dependents.add(
            module
        )

    # --------------------------------------------------

    def ready_nodes(self) -> List[str]:
        """
        Returns nodes whose dependencies
        are already satisfied.
        """

        ready = []

        for node in self.nodes.values():

            if node.completed:

                continue

            if all(
                self.nodes[d].completed
                for d in node.dependencies
            ):
                ready.append(node.name)

        return sorted(ready)

    # --------------------------------------------------

    def mark_completed(
        self,
        module: str,
    ):

        node = self.nodes.get(module)

        if node is None:
            return

        if node.started is None:
            node.started = datetime.now(timezone.utc)

        node.completed = True

        node.finished = datetime.now(timezone.utc)

    # --------------------------------------------------

    def execution_layers(
        self,
    ) -> List[List[str]]:
        """
        Produces execution batches where each
        inner list may execute in parallel.
        """

        indegree = {
            name: len(node.dependencies)
            for name, node in self.nodes.items()
        }

        reverse = defaultdict(set)

        for name, node in self.nodes.items():
            for dep in node.dependencies:
                reverse[dep].add(name)

        queue = deque(
            sorted(
                name
                for name, degree in indegree.items()
                if degree == 0
            )
        )

        layers: List[List[str]] = []

        while queue:

            current_layer = list(queue)

            layers.append(current_layer)

            next_queue = deque()

            while queue:

                current = queue.popleft()

                for dependent in reverse[current]:

                    indegree[dependent] -= 1

                    if indegree[dependent] == 0:

                        next_queue.append(
                            dependent
                        )

            queue = deque(
                sorted(next_queue)
            )

        return layers

    # --------------------------------------------------

    def all_completed(self) -> bool:

        return all(
            node.completed
            for node in self.nodes.values()
        )

    # --------------------------------------------------

    def reset(self):

        for node in self.nodes.values():

            node.completed = False

            node.started = None

            node.finished = None

    # --------------------------------------------------

    def clear(self):

        self.nodes.clear()

    # --------------------------------------------------

    def statistics(self):

        completed = sum(
            node.completed
            for node in self.nodes.values()
        )

        return {

            "initialized": self.initialized,

            "modules": len(self.nodes),

            "completed": completed,

            "remaining":
                len(self.nodes) - completed,

            "parallel_layers":
                len(self.execution_layers()),

        }