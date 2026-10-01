from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_memory.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Memory
Provides dedicated episodic and working memory
storage for individual autonomous agents.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("HERCULE.Agents.AgentMemory")

class AgentMemory:
    """
    Manages local working memory and episodic history for agents.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._memory_store: List[Dict[str, Any]] = []
        logger.info(f"Initialized AgentMemory for agent ID: [{agent_id}]")

    ##################################################
    def store(self, key: str, value: Any, memory_type: str = "working") -> None:
        """
        Store a key-value record in agent memory.
        """
        record = {"key": key, "value": value, "type": memory_type}
        self._memory_store.append(record)
        logger.debug(f"Agent [{self.agent_id}] stored memory key: [{key}]")

    ##################################################
    def retrieve(self, key: str) -> Optional[Any]:
        """
        Retrieve the most recent value for a given memory key.
        """
        for record in reversed(self._memory_store):
            if record["key"] == key:
                return record["value"]
        return None

    ##################################################
    def get_all(self) -> List[Dict[str, Any]]:
        """
        Retrieve all stored memory items.
        """
        return list(self._memory_store)

    ##################################################
    def clear(self) -> None:
        """
        Clear agent memory store.
        """
        self._memory_store.clear()
        logger.debug(f"Cleared memory for agent ID: [{self.agent_id}]")