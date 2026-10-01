from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Working Memory
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from collections import deque
from typing import Any


class WorkingMemory:

    def __init__(self, capacity: int = 20):

        self.capacity = capacity

        self._memory = deque(maxlen=capacity)

    def add(self, item: Any):

        self._memory.append(item)

    def latest(self):

        if not self._memory:
            return None

        return self._memory[-1]

    def get_all(self):

        return list(self._memory)

    def clear(self):

        self._memory.clear()

    def size(self):

        return len(self._memory)