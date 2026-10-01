"""ARC agent adapter for HERCULE's existing reasoning-agent lifecycle."""

from __future__ import annotations

from typing import Any, Callable, Dict

from agents.agent_state import AgentState
from agents.base_agent import BaseAgent
from arc_reasoning.solver import ArcSolver


class ArcReasoningAgent(BaseAgent):
    """Use symbolic ARC rules; optional language advice only ranks verified rules."""

    def __init__(self, agent_id: str = "agent_arc_reasoning_01",
                 advisory_ranker: Callable[[list[dict]], list[str]] | None = None):
        super().__init__(agent_id=agent_id, name="ArcReasoningAgent", role="reasoning")
        self.solver = ArcSolver(advisory_ranker=advisory_ranker)

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        self.set_state(AgentState.THINKING)
        arc_task = task.get("arc_task", task.get("input", task))
        try:
            result = self.solver.solve_json(arc_task)
            status = "success"
        except (KeyError, TypeError, ValueError) as exc:
            result = {"candidates": [], "verified_rules": [],
                      "error": f"{type(exc).__name__}: {exc}"}
            status = "invalid_task"
        finally:
            self.set_state(AgentState.READY)
        return {"status": status, "agent_id": self.agent_id, "arc": result,
                "authority": "deterministic-training-replay-verifier"}

