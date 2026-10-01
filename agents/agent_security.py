from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_security.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Security Layer
Enforces permissions, access controls, and validation
rules for agent actions and resource access.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("HERCULE.Agents.AgentSecurity")

class AgentSecurityGuard:
    """
    Security guard verifying permissions and safe execution constraints.
    """

    def __init__(self):
        self._restricted_roles = {"supervisor", "executor"}
        logger.info("Initialized AgentSecurityGuard.")

    ##################################################
    def validate_action(self, agent_role: str, action: str) -> bool:
        """
        Validate whether an agent role is authorized to perform a specific action.
        """
        logger.debug(f"Validating security for role [{agent_role}] performing action [{action}]")
        if action.startswith("system_") and agent_role not in self._restricted_roles:
            logger.warning(f"Unauthorized system action attempt by role: [{agent_role}]")
            return False
        return True