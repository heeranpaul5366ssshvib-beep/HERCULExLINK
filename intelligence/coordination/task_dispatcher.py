from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Task Dispatcher
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional
from uuid import uuid4


logger = logging.getLogger(__name__)


class TaskPriority(Enum):

    LOW = 1

    NORMAL = 2

    HIGH = 3

    CRITICAL = 4


class TaskStatus(Enum):

    PENDING = "pending"

    RUNNING = "running"

    COMPLETED = "completed"

    FAILED = "failed"

    CANCELLED = "cancelled"


@dataclass
class Task:

    id: str

    name: str

    handler: Callable[..., Any]

    payload: Dict[str, Any] = field(
        default_factory=dict
    )

    priority: TaskPriority = (
        TaskPriority.NORMAL
    )

    created: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    status: TaskStatus = (
        TaskStatus.PENDING
    )

    result: Any = None

    error: Optional[str] = None


class TaskDispatcher:
    """
    Dispatches coordinator tasks to the
    Intelligence Runtime.
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.queue: Deque[Task] = deque()

        self.completed: List[Task] = []

        self.failed: List[Task] = []

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Task Dispatcher"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Task Dispatcher"
        )

        self.queue.clear()

        self.completed.clear()

        self.failed.clear()

        self.initialized = False

    # --------------------------------------------------

    def submit(

        self,

        name: str,

        handler: Callable[..., Any],

        payload: Optional[
            Dict[str, Any]
        ] = None,

        priority: TaskPriority = (
            TaskPriority.NORMAL
        ),

    ) -> str:

        task = Task(

            id=str(uuid4()),

            name=name,

            handler=handler,

            payload=payload or {},

            priority=priority,

        )

        self.queue.append(task)

        logger.debug(
            "Task submitted: %s",
            task.id,
        )

        return task.id

    # --------------------------------------------------

    def dispatch_next(self) -> Optional[Task]:

        if not self.queue:

            return None

        task = self.queue.popleft()

        task.status = TaskStatus.RUNNING

        try:

            task.result = task.handler(
                **task.payload
            )

            task.status = (
                TaskStatus.COMPLETED
            )

            self.completed.append(task)

        except Exception as exc:

            logger.exception(
                "Task failed"
            )

            task.status = (
                TaskStatus.FAILED
            )

            task.error = str(exc)

            self.failed.append(task)

        return task

    # --------------------------------------------------

    def dispatch_all(self):

        results = []

        while self.queue:

            results.append(

                self.dispatch_next()

            )

        return results

    # --------------------------------------------------

    def cancel(

        self,

        task_id: str,

    ) -> bool:

        for task in list(self.queue):

            if task.id == task_id:

                task.status = (
                    TaskStatus.CANCELLED
                )

                self.queue.remove(task)

                return True

        return False

    # --------------------------------------------------

    def pending(self) -> int:

        return len(self.queue)

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized":
                self.initialized,

            "pending":
                len(self.queue),

            "completed":
                len(self.completed),

            "failed":
                len(self.failed),

            "total":

                len(self.queue)

                + len(self.completed)

                + len(self.failed),

        }