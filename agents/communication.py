from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/communication.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Communication Layer
Enables secure message passing, direct communication,
and broadcast events between autonomous agents.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger("HERCULE.Agents.Communication")

class AgentMessage:
    """
    Represents a structured message passed between agents.
    """
    def __init__(self, sender_id: str, recipient_id: str, payload: Dict[str, Any], message_type: str = "direct"):
        self.sender_id = sender_id
        self.recipient_id = recipient_id
        self.payload = payload
        self.message_type = message_type

class AgentCommunicationHub:
    """
    Central hub routing messages between autonomous agents.
    """

    def __init__(self):
        self._inboxes: Dict[str, List[AgentMessage]] = {}
        logger.info("Initialized AgentCommunicationHub.")

    ##################################################
    def send_message(self, message: AgentMessage) -> bool:
        """
        Send a message to a target agent's inbox.
        """
        if message.recipient_id not in self._inboxes:
            self._inboxes[message.recipient_id] = []
        self._inboxes[message.recipient_id].append(message)
        logger.debug(f"Message routed from [{message.sender_id}] to [{message.recipient_id}]")
        return True

    ##################################################
    def get_inbox(self, agent_id: str) -> List[AgentMessage]:
        """
        Retrieve and clear pending messages for a specific agent.
        """
        messages = self._inboxes.get(agent_id, [])
        self._inboxes[agent_id] = []
        return messages