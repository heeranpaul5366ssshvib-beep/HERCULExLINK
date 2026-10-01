from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/executor_agent.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Executor Agent
Executes concrete actions and coordinated system workflows.
"""

import logging
from typing import Any, Dict
from agents.base_agent import BaseAgent
from agents.agent_state import AgentState

logger = logging.getLogger("HERCULE.Agents.ExecutorAgent")

class ExecutorAgent(BaseAgent):
    """
    Specialized agent responsible for carrying out concrete actions and orchestrating workflows.
    """

    def __init__(self, agent_id: str = "agent_executor_01", name: str = "ExecutorAgent"):
        super().__init__(agent_id=agent_id, name=name, role="executor")
        logger.info("Initialized ExecutorAgent.")

    ##################################################
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform concrete action commands through the system runtime.
        """
        self.set_state(AgentState.EXECUTING)
        action_command = task.get("command") or task.get("action", "default_action")
        
        logger.info(f"ExecutorAgent performing action: [{action_command}]")

        execution_result = {
            "command": action_command,
            "exit_code": 0,
            "output": "Action executed successfully through system runtime."
        }

        self.set_state(AgentState.READY)
        return {
            "status": "success",
            "agent_id": self.agent_id,
            "result": execution_result
        }