from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/task_agent.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Task Agent
Manages micro-task execution and workflow tracking.
"""

import logging
from typing import Any, Dict
from agents.base_agent import BaseAgent
from agents.agent_state import AgentState

logger = logging.getLogger("HERCULE.Agents.TaskAgent")

class TaskAgent(BaseAgent):
    """
    Specialized agent for executing and tracking micro-tasks and sub-routines.
    """

    def __init__(self, agent_id: str = "agent_task_01", name: str = "TaskAgent"):
        super().__init__(agent_id=agent_id, name=name, role="task")
        logger.info("Initialized TaskAgent.")

    ##################################################
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute individual micro-tasks and report execution status.
        """
        self.set_state(AgentState.THINKING)
        task_details = task.get("task_item", "Generic Micro-task")
        
        logger.info("TaskAgent tracking micro-task execution...")

        execution_status = {
            "task": task_details,
            "execution_state": "completed",
            "error_code": None
        }

        self.set_state(AgentState.READY)
        return {
            "status": "success",
            "agent_id": self.agent_id,
            "execution": execution_status
        }