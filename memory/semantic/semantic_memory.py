from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Semantic Memory
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any


class SemanticMemory:

    def __init__(self):

        self._knowledge: dict[str, Any] = {}

    def learn(
        self,
        topic: str,
        information: Any,
    ):

        self._knowledge[topic] = information

    def recall(
        self,
        topic: str,
    ):

        return self._knowledge.get(topic)

    def forget(
        self,
        topic: str,
    ):

        self._knowledge.pop(topic, None)

    def topics(self):

        return list(self._knowledge.keys())

    def clear(self):

        self._knowledge.clear()