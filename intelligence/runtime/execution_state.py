from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Execution State
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from datetime import datetime, timezone
from enum import Enum
from typing import Dict


class RuntimeState(Enum):

    CREATED = "created"

    INITIALIZED = "initialized"

    RUNNING = "running"

    WAITING = "waiting"

    PAUSED = "paused"

    COMPLETED = "completed"

    FAILED = "failed"

    CANCELLED = "cancelled"


class ExecutionState:
    """
    Tracks the lifecycle of a runtime
    execution.
    """

    def __init__(self):

        self.state = RuntimeState.CREATED

        self.created = datetime.now(timezone.utc)

        self.started = None

        self.finished = None

        self.error = None

    # --------------------------------------------------

    def initialize(self):

        self.state = RuntimeState.INITIALIZED

    # --------------------------------------------------

    def start(self):

        self.state = RuntimeState.RUNNING

        self.started = datetime.now(timezone.utc)

    # --------------------------------------------------

    def wait(self):

        self.state = RuntimeState.WAITING

    # --------------------------------------------------

    def pause(self):

        self.state = RuntimeState.PAUSED

    # --------------------------------------------------

    def complete(self):

        self.state = RuntimeState.COMPLETED

        self.finished = datetime.now(timezone.utc)

    # --------------------------------------------------

    def fail(

        self,

        error: str,

    ):

        self.state = RuntimeState.FAILED

        self.finished = datetime.now(timezone.utc)

        self.error = error

    # --------------------------------------------------

    def cancel(self):

        self.state = RuntimeState.CANCELLED

        self.finished = datetime.now(timezone.utc)

    # --------------------------------------------------

    @property
    def is_running(self):

        return self.state == RuntimeState.RUNNING

    # --------------------------------------------------

    @property
    def is_finished(self):

        return self.state in {

            RuntimeState.COMPLETED,

            RuntimeState.FAILED,

            RuntimeState.CANCELLED,

        }

    # --------------------------------------------------

    def statistics(self) -> Dict[str, object]:

        duration = None

        if self.started and self.finished:

            duration = (

                self.finished -

                self.started

            ).total_seconds()

        return {

            "state": self.state.value,

            "created": self.created.isoformat(),

            "started": (

                self.started.isoformat()

                if self.started

                else None

            ),

            "finished": (

                self.finished.isoformat()

                if self.finished

                else None

            ),

            "duration": duration,

            "error": self.error,

        }