from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Coordinator State
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class CoordinatorState(Enum):
    """
    Coordinator lifecycle states.
    """

    CREATED = "created"

    INITIALIZING = "initializing"

    READY = "ready"

    RUNNING = "running"

    WAITING = "waiting"

    PAUSED = "paused"

    STOPPING = "stopping"

    STOPPED = "stopped"

    ERROR = "error"


@dataclass
class StateTransition:

    from_state: CoordinatorState

    to_state: CoordinatorState

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    reason: str = ""


class CoordinatorStateManager:
    """
    Maintains the runtime lifecycle of the
    Intelligence Coordinator.
    """

    def __init__(self):

        self.state = CoordinatorState.CREATED

        self.created = datetime.now(timezone.utc)

        self.updated = self.created

        self.transitions: List[StateTransition] = []

        self.last_error: Optional[str] = None

    # --------------------------------------------------

    def transition(

        self,

        new_state: CoordinatorState,

        reason: str = "",

    ) -> None:

        transition = StateTransition(

            from_state=self.state,

            to_state=new_state,

            reason=reason,

        )

        self.transitions.append(
            transition
        )

        self.state = new_state

        self.updated = datetime.now(timezone.utc)

    # --------------------------------------------------

    def initialize(self):

        self.transition(

            CoordinatorState.INITIALIZING,

            "Initialization started",

        )

    # --------------------------------------------------

    def ready(self):

        self.transition(

            CoordinatorState.READY,

            "Coordinator ready",

        )

    # --------------------------------------------------

    def start(self):

        self.transition(

            CoordinatorState.RUNNING,

            "Execution started",

        )

    # --------------------------------------------------

    def wait(self):

        self.transition(

            CoordinatorState.WAITING,

            "Waiting for task",

        )

    # --------------------------------------------------

    def pause(self):

        self.transition(

            CoordinatorState.PAUSED,

            "Execution paused",

        )

    # --------------------------------------------------

    def stop(self):

        self.transition(

            CoordinatorState.STOPPING,

            "Shutdown requested",

        )

    # --------------------------------------------------

    def stopped(self):

        self.transition(

            CoordinatorState.STOPPED,

            "Coordinator stopped",

        )

    # --------------------------------------------------

    def error(

        self,

        message: str,

    ):

        self.last_error = message

        self.transition(

            CoordinatorState.ERROR,

            message,

        )

    # --------------------------------------------------

    @property
    def is_running(self):

        return self.state == CoordinatorState.RUNNING

    # --------------------------------------------------

    @property
    def is_ready(self):

        return self.state == CoordinatorState.READY

    # --------------------------------------------------

    @property
    def has_error(self):

        return self.state == CoordinatorState.ERROR

    # --------------------------------------------------

    def history(self):

        return [

            {

                "from": t.from_state.value,

                "to": t.to_state.value,

                "timestamp": t.timestamp.isoformat(),

                "reason": t.reason,

            }

            for t in self.transitions

        ]

    # --------------------------------------------------

    def statistics(self) -> Dict[str, Any]:

        return {

            "state": self.state.value,

            "created": self.created.isoformat(),

            "updated": self.updated.isoformat(),

            "transitions": len(

                self.transitions

            ),

            "last_error": self.last_error,

        }