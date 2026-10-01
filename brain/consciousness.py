from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Consciousness
Author: Heeran Paul
License: MIT
--------------------------------------------

Internal runtime-state tracker (NOT human consciousness, NOT sentience).
Records the Brain's lifecycle position so operators and tests can see
where a request is: IDLE/LISTENING/UNDERSTANDING/RECALLING/THINKING/
REASONING/PLANNING/DECIDING/EXECUTING/OBSERVING/VERIFYING/REFLECTING/
RECOVERING/WAITING/COMPLETED/ERROR. No emotions, dreams, or
self-awareness claims — only observable executive state.
"""

from datetime import datetime, timezone


VALID_STATES = (
    "IDLE",
    "ACTIVE",
    "AUTONOMOUS",
    "LISTENING",
    "UNDERSTANDING",
    "RECALLING",
    "THINKING",
    "REASONING",
    "PLANNING",
    "DECIDING",
    "EXECUTING",
    "OBSERVING",
    "VERIFYING",
    "REFLECTING",
    "RECOVERING",
    "WAITING",
    "COMPLETED",
    "SPEAKING",
    "ERROR",
)

# Allowed transitions keep the lifecycle honest; violations raise loudly
# instead of silently misreporting state.
_ALLOWED = {
    "IDLE": {"ACTIVE", "AUTONOMOUS", "LISTENING", "UNDERSTANDING", "THINKING", "PLANNING", "ERROR"},
    "ACTIVE": {"LISTENING", "UNDERSTANDING", "RECALLING", "THINKING", "REASONING",
               "PLANNING", "DECIDING", "AUTONOMOUS", "IDLE", "ERROR", "SPEAKING"},
    "AUTONOMOUS": {"UNDERSTANDING", "EXECUTING", "WAITING", "IDLE", "ACTIVE", "ERROR"},
    "LISTENING": {"UNDERSTANDING", "THINKING", "IDLE", "ERROR"},
    "UNDERSTANDING": {"RECALLING", "THINKING", "REASONING", "PLANNING", "IDLE", "ERROR"},
    "RECALLING": {"REASONING", "THINKING", "PLANNING", "IDLE", "ERROR"},
    "THINKING": {"ACTIVE", "IDLE", "ERROR"},
    "REASONING": {"RECALLING", "PLANNING", "DECIDING", "ACTIVE", "IDLE", "ERROR"},
    "PLANNING": {"DECIDING", "EXECUTING", "ERROR", "IDLE"},
    "DECIDING": {"EXECUTING", "PLANNING", "IDLE", "ERROR"},
    "EXECUTING": {"OBSERVING", "VERIFYING", "ERROR", "RECOVERING", "WAITING", "SPEAKING"},
    "OBSERVING": {"VERIFYING", "ERROR", "RECOVERING"},
    "VERIFYING": {"REFLECTING", "ERROR", "RECOVERING", "EXECUTING", "OBSERVING"},
    "REFLECTING": {"COMPLETED", "ACTIVE", "IDLE", "ERROR", "SPEAKING"},
    "COMPLETED": {"ACTIVE", "IDLE", "LISTENING", "SPEAKING"},
    "SPEAKING": {"IDLE", "ACTIVE", "LISTENING", "ERROR"},
    "WAITING": {"EXECUTING", "PLANNING", "AUTONOMOUS", "IDLE", "ERROR"},
    "ERROR": {"RECOVERING", "IDLE", "ACTIVE"},
    "RECOVERING": {"EXECUTING", "PLANNING", "IDLE", "ERROR", "ACTIVE"},
}


class Consciousness:

    """
    Executive awareness layer.

    Responsible for

    • Current State
    • Focus
    • Attention
    • Context
    """

    def __init__(self):

        self.state = "IDLE"

        self.focus = None

        self.context = {}

        self.state_history: list[dict] = []
        self._record("IDLE", "init")

    ##################################################

    def _record(self, state, reason=""):

        self.state_history.append({
            "state": state,
            "at": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason)[:160],
            "focus": str(self.focus)[:120] if self.focus is not None else None,
        })
        if len(self.state_history) > 200:
            del self.state_history[: len(self.state_history) - 200]

    def set_state(

        self,

        state,

        reason="",

    ):

        state = str(state).upper()
        if state not in VALID_STATES:
            raise ValueError(f"unknown consciousness state: {state!r}")
        # ERROR/RECOVERING/IDLE/ACTIVE are always reachable (safety valve);
        # other jumps must follow the lifecycle graph.
        if state not in ("ERROR", "RECOVERING", "IDLE", "ACTIVE"):
            allowed = _ALLOWED.get(self.state, set())
            if state not in allowed:
                raise ValueError(
                    f"illegal consciousness transition {self.state} -> {state}"
                )
        self.state = state
        self._record(state, reason)

    def transition(self, state, reason=""):
        """Explicit lifecycle transition (same rules as set_state)."""
        self.set_state(state, reason)
        return self.state

    ##################################################

    def get_state(self):

        return self.state

    ##################################################

    def focus_on(

        self,

        target,

    ):

        self.focus = target

    ##################################################

    def current_focus(self):

        return self.focus

    ##################################################

    def remember(

        self,

        key,

        value,

    ):

        self.context[key] = value

    ##################################################

    def recall(

        self,

        key,

    ):

        return self.context.get(

            key,

        )

    ##################################################

    def clear(self):

        self.context.clear()

        self.focus = None

        self.state = "IDLE"