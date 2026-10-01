from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: agents/agent_metrics.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Agent Metrics
Tracks performance, execution latency, success rates,
and operational telemetry for autonomous agents.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("HERCULE.Agents.AgentMetrics")

class AgentMetricsCollector:
    """
    Collects and aggregates runtime metrics for agents.
    """

    def __init__(self):
        self._metrics: Dict[str, Dict[str, Any]] = {}
        logger.info("Initialized AgentMetricsCollector.")

    ##################################################
    def record_execution(self, agent_id: str, latency: float, success: bool) -> None:
        """
        Record execution telemetry for an agent.
        """
        if agent_id not in self._metrics:
            self._metrics[agent_id] = {
                "total_runs": 0,
                "successes": 0,
                "failures": 0,
                "total_latency": 0.0
            }
        
        stats = self._metrics[agent_id]
        stats["total_runs"] += 1
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1
        stats["total_latency"] += latency
        logger.debug(f"Recorded metrics for agent [{agent_id}] (Latency: {latency}s, Success: {success})")

    ##################################################
    def get_metrics(self, agent_id: str) -> Dict[str, Any]:
        """
        Retrieve aggregated metrics for an agent.
        """
        stats = self._metrics.get(agent_id, {"total_runs": 0, "successes": 0, "failures": 0, "total_latency": 0.0})
        runs = stats["total_runs"]
        avg_latency = (stats["total_latency"] / runs) if runs > 0 else 0.0
        success_rate = (stats["successes"] / runs) if runs > 0 else 0.0

        return {
            "agent_id": agent_id,
            "total_runs": runs,
            "success_rate": success_rate,
            "average_latency": avg_latency
        }