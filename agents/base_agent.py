from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/base_agent.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Base Agent Framework
Provides the foundational abstract class for all
specialized autonomous agents within HERCULE.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from agents.agent_state import AgentState
from agents.agent_context import AgentContext

logger = logging.getLogger("HERCULE.Agents.BaseAgent")

class BaseAgent(ABC):
    """
    Abstract base class for all HERCULE autonomous agents.
    Defines the common lifecycle, state management, and execution interface.
    """

    def __init__(self, agent_id: str, name: str, role: str):
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.state = AgentState.IDLE
        self.context = AgentContext()
        logger.info(f"Initialized agent [{self.name}] with ID [{self.agent_id}] and role [{self.role}]")

    ##################################################
    def set_state(self, new_state: AgentState) -> None:
        """
        Update the current state of the agent.
        """
        old_state = self.state
        self.state = new_state
        logger.debug(f"Agent [{self.name}] state changed: {old_state} -> {new_state}")

    ##################################################
    def get_state(self) -> AgentState:
        """
        Retrieve the current state of the agent.
        """
        return self.state

    ##################################################
    def update_context(self, key: str, value: Any) -> None:
        """
        Update the agent execution context with new data.
        """
        self.context.set(key, value)
        logger.debug(f"Agent [{self.name}] context updated for key: [{key}]")

    ##################################################
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        Retrieve data from the agent execution context.
        """
        return self.context.get(key, default)

    ##################################################
    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Core execution method to be implemented by specialized agents.
        """
        pass

    ##################################################
    def initialize(self) -> bool:
        """
        Perform any necessary startup routines for the agent.
        """
        self.set_state(AgentState.INITIALIZING)
        logger.info(f"Agent [{self.name}] is initializing...")
        self.set_state(AgentState.IDLE)
        return True

    ##################################################
    def shutdown(self) -> bool:
        """
        Perform clean up during agent shutdown.
        """
        self.set_state(AgentState.SHUTTING_DOWN)
        logger.info(f"Agent [{self.name}] is shutting down...")
        self.set_state(AgentState.TERMINATED)
        return True