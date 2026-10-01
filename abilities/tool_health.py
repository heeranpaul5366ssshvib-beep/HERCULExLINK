from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Tool Health & Performance
Author: Heeran Paul
License: MIT
--------------------------------------------

Live tool health (AVAILABLE/READY/DEGRADED/UNAVAILABLE/FAILED) over
the ability registry plus measured per-tool reliability. Health is
observed, never assumed from configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ToolHealth(str, Enum):
    AVAILABLE = "available"
    READY = "ready"
    LOADING = "loading"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass
class ToolPerformance:
    tool_name: str
    samples: int = 0
    successes: int = 0
    failures: int = 0
    latency_ewma_ms: float = 0.0

    def success_rate(self, prior_ok: float = 2.0, prior_total: float = 4.0) -> float:
        total = self.samples + prior_total
        return (self.successes + prior_ok) / total if total else 0.5

    def as_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool_name, "samples": self.samples, "successes": self.successes,
                "failures": self.failures, "success_rate": round(self.success_rate(), 3),
                "latency_ewma_ms": round(self.latency_ewma_ms, 3)}


class ToolPerformanceTracker:
    """Aggregate tool outcomes; priors prevent single-anomaly distortion."""

    def __init__(self, ewma_alpha: float = 0.3):
        self.ewma_alpha = ewma_alpha
        self._stats: Dict[str, ToolPerformance] = {}

    def record(self, tool_name: str, success: bool, latency_ms: float = 0.0) -> ToolPerformance:
        perf = self._stats.setdefault(tool_name, ToolPerformance(tool_name))
        perf.samples += 1
        if success:
            perf.successes += 1
        else:
            perf.failures += 1
        latency_ms = max(0.0, float(latency_ms or 0.0))
        perf.latency_ewma_ms = latency_ms if perf.latency_ewma_ms <= 0 else (
            self.ewma_alpha * latency_ms + (1.0 - self.ewma_alpha) * perf.latency_ewma_ms)
        return perf

    def stats_for(self, tool_name: str) -> ToolPerformance:
        return self._stats.get(tool_name, ToolPerformance(tool_name))


class ToolHealthMonitor:
    """Probe ability + agent health without changing their state."""

    def __init__(self, failure_threshold: int = 3, degraded_failure_rate: float = 0.4,
                 tracker: Optional[ToolPerformanceTracker] = None):
        self.failure_threshold = failure_threshold
        self.degraded_failure_rate = degraded_failure_rate
        self.tracker = tracker or ToolPerformanceTracker()
        self._consecutive_failures: Dict[str, int] = {}

    def check_tool(self, name: str, ability_manager=None) -> Dict[str, Any]:
        ability = ability_manager.get(name) if ability_manager is not None else None
        if ability is None:
            return {"name": name, "kind": "tool", "state": ToolHealth.UNAVAILABLE.value, "reason": "not registered"}
        if not getattr(ability, "enabled", True):
            return {"name": name, "kind": "tool", "state": ToolHealth.UNAVAILABLE.value, "reason": "disabled"}
        perf = self.tracker.stats_for(name)
        if self._consecutive_failures.get(name, 0) >= self.failure_threshold:
            state = ToolHealth.FAILED
        elif perf.samples >= 3 and (perf.failures / perf.samples) >= self.degraded_failure_rate:
            state = ToolHealth.DEGRADED
        else:
            state = ToolHealth.READY
        return {"name": name, "kind": "tool", "state": state.value,
                "success_rate": round(perf.success_rate(), 3), "samples": perf.samples}

    def check_agent(self, agent_id: str, agent_manager=None) -> Dict[str, Any]:
        agent = agent_manager.get_agent(agent_id) if agent_manager is not None else None
        if agent is None:
            return {"name": agent_id, "kind": "agent", "state": ToolHealth.UNAVAILABLE.value, "reason": "not registered"}
        raw = str(getattr(getattr(agent, "state", None), "name", getattr(agent, "state", "READY"))).upper()
        mapping = {"READY": ToolHealth.READY, "IDLE": ToolHealth.READY, "BUSY": ToolHealth.READY,
                   "THINKING": ToolHealth.READY, "EXECUTING": ToolHealth.READY, "WAITING": ToolHealth.READY,
                   "PAUSED": ToolHealth.DEGRADED, "INITIALIZING": ToolHealth.LOADING,
                   "ERROR": ToolHealth.FAILED, "TERMINATED": ToolHealth.UNAVAILABLE,
                   "SHUTTING_DOWN": ToolHealth.UNAVAILABLE, "OFFLINE": ToolHealth.UNAVAILABLE}
        state = mapping.get(raw, ToolHealth.LOADING)
        return {"name": agent_id, "kind": "agent", "state": state.value, "agent_state": raw}

    def note_failure(self, name: str) -> None:
        self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1

    def note_success(self, name: str) -> None:
        self._consecutive_failures[name] = 0
