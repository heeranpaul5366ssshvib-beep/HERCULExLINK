from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_config.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Configuration Manager
Centralizes default parameters, model assignments,
and threshold configurations for the agent ecosystem.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("HERCULE.Agents.AgentConfig")

class AgentConfigManager:
    """
    Manages configuration settings and parameters for agents.
    """

    def __init__(self):
        self._config: Dict[str, Any] = {
            "default_timeout": 30,
            "max_retries": 3,
            "log_level": "INFO",
            "cooperative_mode": True
        }
        logger.info("Initialized AgentConfigManager.")

    ##################################################
    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a configuration value by key.
        """
        return self._config.get(key, default)

    ##################################################
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.
        """
        self._config[key] = value
        logger.debug(f"Agent config updated: [{key}] = {value}")