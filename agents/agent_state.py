from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_state.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent State Definitions
Defines the enumeration of possible operational
states for HERCULE autonomous agents.
"""

from enum import Enum, auto

class AgentState(Enum):
    """
    Enumeration representing the lifecycle and operational
    states of an autonomous agent within HERCULE.
    """
    INITIALIZING = auto()
    IDLE = auto()
    READY = auto()
    BUSY = auto()
    THINKING = auto()
    EXECUTING = auto()
    WAITING = auto()
    ERROR = auto()
    PAUSED = auto()
    SHUTTING_DOWN = auto()
    TERMINATED = auto()