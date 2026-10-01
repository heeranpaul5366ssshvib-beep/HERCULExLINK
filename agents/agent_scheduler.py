from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_scheduler.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Scheduler
Manages asynchronous task queuing and priority
scheduling for agent execution workflows.
"""

import logging
import queue
from typing import Any, Dict, Optional

logger = logging.getLogger("HERCULE.Agents.AgentScheduler")

class AgentScheduler:
    """
    Scheduler for prioritizing and queuing agent tasks.
    """

    def __init__(self):
        self._task_queue: queue.PriorityQueue = queue.PriorityQueue()
        logger.info("Initialized AgentScheduler.")

    ##################################################
    def schedule_task(self, priority: int, agent_id: str, task_payload: Dict[str, Any]) -> None:
        """
        Schedule a task with a given priority level (lower number = higher priority).
        """
        item = (priority, {"agent_id": agent_id, "payload": task_payload})
        self._task_queue.put(item)
        logger.debug(f"Scheduled task for agent [{agent_id}] with priority [{priority}]")

    ##################################################
    def next_task(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the next highest-priority task from the queue.
        """
        if self._task_queue.empty():
            return None
        _, task_data = self._task_queue.get()
        return task_data

    ##################################################
    def is_empty(self) -> bool:
        """
        Check if the task queue is empty.
        """
        return self._task_queue.empty()