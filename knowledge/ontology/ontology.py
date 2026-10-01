from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Ontology
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from collections import defaultdict


class Ontology:
    """
    Represents relationships between concepts.
    """

    def __init__(self):

        self._graph = defaultdict(set)

    ##################################################

    def add_concept(
        self,
        concept: str,
    ):

        self._graph[concept]

    ##################################################

    def relate(
        self,
        source: str,
        target: str,
    ):

        self._graph[source].add(target)

    ##################################################

    def relationships(
        self,
        concept: str,
    ):

        return list(
            self._graph.get(concept, set())
        )

    ##################################################

    def concepts(self):

        return list(self._graph.keys())

    ##################################################

    def remove(
        self,
        concept: str,
    ):

        self._graph.pop(concept, None)

        for values in self._graph.values():

            values.discard(concept)

    ##################################################

    def clear(self):

        self._graph.clear()