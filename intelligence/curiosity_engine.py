from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Curiosity Engine
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List
from uuid import uuid4


logger = logging.getLogger(__name__)


class CuriosityPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExplorationGoal:

    id: str

    title: str

    description: str

    priority: CuriosityPriority

    created: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    completed: bool = False

    metadata: Dict[str, Any] = field(
        default_factory=dict
    )


class CuriosityEngine:
    """
    Autonomous exploration engine.

    Responsibilities

    • Detect knowledge gaps
    • Generate research goals
    • Prioritize exploration
    • Track unanswered questions
    • Drive autonomous learning
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

        self.history: List[Dict[str, Any]] = []

        self.goals: Dict[str, ExplorationGoal] = {}

    # --------------------------------------------------

    def initialize(self):

        logger.info(
            "Initializing Curiosity Engine"
        )

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info(
            "Stopping Curiosity Engine"
        )

        self.goals.clear()

        self.history.clear()

        self.initialized = False

    # --------------------------------------------------

    def process(
        self,
        pipeline: Dict[str, Any],
    ) -> Dict[str, Any]:

        gaps = self.detect_knowledge_gaps(
            pipeline
        )

        created = []

        for gap in gaps:

            goal = self.create_goal(

                title=gap,

                description=(
                    f"Investigate knowledge gap: {gap}"
                ),

                priority=CuriosityPriority.MEDIUM,

            )

            created.append(goal.id)

        result = {

            "timestamp": datetime.now(timezone.utc).isoformat(),

            "knowledge_gaps": gaps,

            "new_goals": created,

            "total_goals": len(self.goals),

        }

        self.history.append(result)

        return result

    # --------------------------------------------------

    def detect_knowledge_gaps(
        self,
        pipeline: Dict[str, Any],
    ) -> List[str]:

        gaps = []

        required = [

            "concepts",

            "reasoning",

            "prediction",

            "world_model",

        ]

        for item in required:

            if item not in pipeline:

                gaps.append(item)

        return gaps

    # --------------------------------------------------

    def create_goal(

        self,

        title: str,

        description: str,

        priority: CuriosityPriority,

    ) -> ExplorationGoal:

        goal = ExplorationGoal(

            id=str(uuid4()),

            title=title,

            description=description,

            priority=priority,

        )

        self.goals[goal.id] = goal

        return goal

    # --------------------------------------------------

    def complete_goal(
        self,
        goal_id: str,
    ):

        goal = self.goals.get(goal_id)

        if goal:

            goal.completed = True

    # --------------------------------------------------

    def pending_goals(
        self,
    ) -> List[ExplorationGoal]:

        return [

            goal

            for goal in self.goals.values()

            if not goal.completed

        ]

    # --------------------------------------------------

    def completed_goals(
        self,
    ) -> List[ExplorationGoal]:

        return [

            goal

            for goal in self.goals.values()

            if goal.completed

        ]

    # --------------------------------------------------

    def remove_goal(
        self,
        goal_id: str,
    ):

        self.goals.pop(goal_id, None)

    # --------------------------------------------------

    def clear_goals(self):

        self.goals.clear()

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "history": len(self.history),

            "total_goals": len(self.goals),

            "pending": len(

                self.pending_goals()

            ),

            "completed": len(

                self.completed_goals()

            ),

        }