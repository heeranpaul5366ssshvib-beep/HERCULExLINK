from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Kernel Context
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from dataclasses import dataclass, field
from typing import Any


@dataclass
class KernelContext:
    """
    Shared runtime context for all services.
    """

    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)

    def contains(self, key: str) -> bool:
        return key in self.metadata

    def remove(self, key: str) -> None:
        self.metadata.pop(key, None)

    def clear(self) -> None:
        self.metadata.clear()