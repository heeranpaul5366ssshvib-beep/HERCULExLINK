from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/conversation_agent.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Conversation Agent
Manages natural language dialogue and interaction.
"""

import logging
from typing import Any, Dict
from agents.base_agent import BaseAgent
from agents.agent_state import AgentState

logger = logging.getLogger("HERCULE.Agents.ConversationAgent")

class ConversationAgent(BaseAgent):
    """
    Specialized agent for managing conversational turns and user interactions.
    """

    def __init__(self, agent_id: str = "agent_conversation_01", name: str = "ConversationAgent"):
        super().__init__(agent_id=agent_id, name=name, role="conversation")
        logger.info("Initialized ConversationAgent.")

    ##################################################
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate contextual natural language responses for user dialogues.
        """
        self.set_state(AgentState.THINKING)
        message = task.get("message") or task.get("prompt", "Hello")
        
        logger.info("ConversationAgent generating response for message...")

        response_payload = {
            "response": "Hercule OS acknowledgment: Received message context.",
            "tone": "professional"
        }

        self.set_state(AgentState.READY)
        return {
            "status": "success",
            "agent_id": self.agent_id,
            "data": response_payload
        }