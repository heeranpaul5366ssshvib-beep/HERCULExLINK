from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_manager.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Manager
Coordinates the initialization, execution lifecycle,
and management of autonomous agents in HERCULE.
"""

import logging
from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent
from agents.agent_registry import AgentRegistry
from agents.agent_state import AgentState

logger = logging.getLogger("HERCULE.Agents.AgentManager")

class AgentManager:
    """
    Central manager for HERCULE autonomous agents, responsible for
    registry coordination, lifecycle management, and task routing.
    """

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry()
        logger.info("Initialized AgentManager.")

    ##################################################
    def register_agent(self, agent: BaseAgent) -> None:
        """
        Register an agent with the system registry.
        """
        self.registry.register(agent)

    ##################################################
    def unregister_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Unregister an agent from the system registry.
        """
        return self.registry.unregister(agent_id)

    ##################################################
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Retrieve an agent instance by ID.
        """
        return self.registry.get(agent_id)

    ##################################################
    def initialize_all(self) -> bool:
        """
        Initialize all registered agents.
        """
        logger.info("Initializing all registered agents...")
        for agent_id, agent in self.registry.all().items():
            try:
                agent.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize agent [{agent_id}]: {e}")
                agent.set_state(AgentState.ERROR)
        logger.info("All agents initialization sequence completed.")
        return True

    ##################################################
    def shutdown_all(self) -> bool:
        """
        Shutdown all registered agents.
        """
        logger.info("Shutting down all registered agents...")
        for agent_id, agent in self.registry.all().items():
            try:
                agent.shutdown()
            except Exception as e:
                logger.error(f"Failed to shutdown agent [{agent_id}]: {e}")
        logger.info("All agents shutdown sequence completed.")
        return True

    ##################################################
    def execute_task(self, agent_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task using a specific agent.
        """
        agent = self.registry.get(agent_id)
        if not agent:
            error_msg = f"Agent with ID [{agent_id}] not found for execution."
            logger.error(error_msg)
            return {"status": "error", "error": error_msg}

        try:
            agent.set_state(AgentState.BUSY)
            logger.info(f"Executing task on agent [{agent.name}] (ID: {agent_id})")
            result = agent.execute(task)
            agent.set_state(AgentState.READY)
            return result
        except Exception as e:
            logger.error(f"Error during task execution on agent [{agent_id}]: {e}")
            agent.set_state(AgentState.ERROR)
            return {"status": "error", "error": str(e)}