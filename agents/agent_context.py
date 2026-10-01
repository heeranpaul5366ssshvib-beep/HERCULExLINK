from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_context.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Context
Minimal execution-context container required by BaseAgent
(set/get/clear). Restored in Phase J: the module was an empty
placeholder that broke every agents.* import.
"""

from typing import Any, Dict, Optional


class AgentContext:
    """Small key/value execution context for one agent."""

    def __init__(self, initial: Optional[Dict[str, Any]] = None):
        self._data: Dict[str, Any] = dict(initial or {})

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self) -> None:
        self._data.clear()

    def all(self) -> Dict[str, Any]:
        return dict(self._data)
