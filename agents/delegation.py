from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/delegation.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Delegation Layer
Manages task decomposition and assignment from
coordinators/supervisors to specialized execution agents.
"""

import logging
from typing import Any, Dict
from agents.agent_manager import AgentManager

logger = logging.getLogger("HERCULE.Agents.Delegation")

class TaskDelegator:
    """
    Handles dynamic task routing and delegation across specialized agents.
    """

    def __init__(self, agent_manager: AgentManager):
        self.agent_manager = agent_manager
        logger.info("Initialized TaskDelegator.")

    ##################################################
    def delegate(self, agent_id: str, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegate a task payload directly to a specified target agent ID.
        """
        logger.info(f"Delegating task to agent ID: [{agent_id}]")
        return self.agent_manager.execute_task(agent_id, task_payload)

    ##################################################
    def auto_delegate(self, role: str, task_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically discover an available agent matching a role and delegate the task.
        """
        matching_agents = self.agent_manager.registry.get_by_role(role)
        if not matching_agents:
            error_msg = f"No available agents found for role: [{role}]"
            logger.error(error_msg)
            return {"status": "error", "error": error_msg}
        
        target_agent = matching_agents[0]
        logger.info(f"Auto-delegating task to agent [{target_agent.name}] (Role: {role})")
        return self.agent_manager.execute_task(target_agent.agent_id, task_payload)