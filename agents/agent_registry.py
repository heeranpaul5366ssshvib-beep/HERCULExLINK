from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_registry.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Registry
Manages the registration, lookup, and lifecycle
tracking of all autonomous agents in HERCULE.
"""

import logging
from typing import Dict, List, Optional
from agents.base_agent import BaseAgent

logger = logging.getLogger("HERCULE.Agents.AgentRegistry")

class AgentRegistry:
    """
    Registry for storing, discovering, and managing agent instances
    within the HERCULE autonomous framework.
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        logger.info("Initialized AgentRegistry.")

    ##################################################
    def register(self, agent: BaseAgent) -> None:
        """
        Register a new agent instance in the registry.
        """
        if agent.agent_id in self._agents:
            logger.warning(f"Agent with ID [{agent.agent_id}] is already registered. Overwriting.")
        self._agents[agent.agent_id] = agent
        logger.info(f"Registered agent: [{agent.name}] (ID: {agent.agent_id}, Role: {agent.role})")

    ##################################################
    def unregister(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Unregister and remove an agent by its ID.
        """
        agent = self._agents.pop(agent_id, None)
        if agent:
            logger.info(f"Unregistered agent with ID: [{agent_id}]")
        else:
            logger.warning(f"Attempted to unregister non-existent agent ID: [{agent_id}]")
        return agent

    ##################################################
    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """
        Retrieve an agent instance by its ID.
        """
        return self._agents.get(agent_id)

    ##################################################
    def get_by_role(self, role: str) -> List[BaseAgent]:
        """
        Retrieve all agents matching a specific role.
        """
        matching_agents = [agent for agent in self._agents.values() if agent.role == role]
        logger.debug(f"Found {len(matching_agents)} agents for role: [{role}]")
        return matching_agents

    ##################################################
    def all(self) -> Dict[str, BaseAgent]:
        """
        Retrieve a dictionary of all registered agents.
        """
        return dict(self._agents)

    ##################################################
    def clear(self) -> None:
        """
        Clear all registered agents.
        """
        self._agents.clear()
        logger.info("AgentRegistry cleared.")