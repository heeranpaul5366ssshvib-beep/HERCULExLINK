from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/planner_agent.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Planner Agent
Decomposes complex goals and objectives into structured,
step-by-step execution plans.
"""

import logging
from typing import Any, Dict, List
from agents.base_agent import BaseAgent
from agents.agent_state import AgentState

logger = logging.getLogger("HERCULE.Agents.PlannerAgent")

class PlannerAgent(BaseAgent):
    """
    Specialized agent responsible for strategic task decomposition,
    sequencing, and planning within HERCULE.
    """

    def __init__(self, agent_id: str = "agent_planner_01", name: str = "PlannerAgent"):
        super().__init__(agent_id=agent_id, name=name, role="planner")
        logger.info("Initialized PlannerAgent.")

    ##################################################
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decompose a high-level goal or task into a structured execution plan.
        """
        self.set_state(AgentState.THINKING)
        objective = task.get("objective") or task.get("prompt", "Default System Objective")
        
        logger.info(f"PlannerAgent formulating strategy for objective: [{objective}]")

        # Generate structured plan steps
        plan_steps = [
            {
                "step_id": 1,
                "action": "Analyze and validate objective constraints",
                "status": "ready"
            },
            {
                "step_id": 2,
                "action": "Deconstruct goal into domain-specific sub-tasks",
                "status": "pending"
            },
            {
                "step_id": 3,
                "action": "Assign sub-tasks to specialized execution agents",
                "status": "pending"
            }
        ]

        self.update_context("last_objective", objective)
        self.update_context("last_plan", plan_steps)
        
        self.set_state(AgentState.READY)
        return {
            "status": "success",
            "agent_id": self.agent_id,
            "objective": objective,
            "plan": plan_steps
        }