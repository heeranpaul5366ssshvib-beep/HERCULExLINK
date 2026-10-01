from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Long Term Memory
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from typing import Any


class LongTermMemory:

    def __init__(self):

        self._memory: dict[str, Any] = {}

    def store(
        self,
        key: str,
        value: Any,
    ) -> None:

        self._memory[key] = value

    def retrieve(
        self,
        key: str,
    ) -> Any:

        return self._memory.get(key)

    def exists(
        self,
        key: str,
    ) -> bool:

        return key in self._memory

    def delete(
        self,
        key: str,
    ) -> None:

        self._memory.pop(key, None)

    def all(self):

        return self._memory.copy()

    def clear(self):

        self._memory.clear()