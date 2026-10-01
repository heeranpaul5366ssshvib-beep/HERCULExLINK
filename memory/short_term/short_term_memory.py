from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Short Term Memory
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any


class ShortTermMemory:

    def __init__(self):

        self._memory: list[Any] = []

    def add(self, item: Any):

        self._memory.append(item)

    def get(self):

        return self._memory.copy()

    def last(self):

        if not self._memory:
            return None

        return self._memory[-1]

    def clear(self):

        self._memory.clear()

    def size(self):

        return len(self._memory)