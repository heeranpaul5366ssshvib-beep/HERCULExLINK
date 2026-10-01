from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Cognition Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from cognition.planner.planner import Planner
from cognition.reasoning.reasoner import Reasoner
from cognition.decision.decision_engine import DecisionEngine
from cognition.goals.goal_manager import GoalManager

from memory.memory_manager import MemoryManager
from models.model_manager import ModelManager


class CognitionManager:
    """
    Central controller for HERCULE cognition.

    Coordinates:
    - Planning
    - Reasoning
    - Decision Making
    - Goal Management
    """

    def __init__(
        self,
        model_manager: ModelManager,
        memory_manager: MemoryManager,
    ):

        self.models = model_manager

        self.memory = memory_manager

        self.planner = Planner()

        self.reasoner = Reasoner(
            model_manager,
        )

        self.decision = DecisionEngine()

        self.goals = GoalManager()

    ##################################################

    def think(
        self,
        prompt: str,
    ) -> str:

        response = self.reasoner.think(prompt)

        self.memory.remember(
            {
                "prompt": prompt,
                "response": response,
            }
        )

        return response

    ##################################################

    def explain(
        self,
        topic: str,
    ):

        return self.reasoner.explain(topic)

    ##################################################

    def solve(
        self,
        problem: str,
    ):

        return self.reasoner.solve(problem)

    ##################################################

    def create_plan(
        self,
        goal: str,
        steps: list[str],
    ):

        return self.planner.create_plan(
            goal,
            steps,
        )

    ##################################################

    def choose(
        self,
        options,
        scores=None,
    ):

        return self.decision.choose(
            options,
            scores,
        )

    ##################################################

    def add_goal(
        self,
        name,
        description,
    ):

        self.goals.add(
            name,
            description,
        )

    ##################################################

    def health(self):

        return {

            "working_memory": self.memory.health(),

            "active_goals": len(
                self.goals.active()
            ),

            "plans": len(
                self.planner.current_plan
            ),

            "decisions": len(
                self.decision.history
            ),

        }