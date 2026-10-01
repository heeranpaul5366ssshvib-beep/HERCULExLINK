from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: External Benchmark Registry (UAI Phase M14/M15)
Author: Heeran Paul
License: MIT
--------------------------------------------

Machine-readable registry of EXTERNAL benchmarks. An adapter entry
existing here does NOT mean the benchmark ran: ``execution_status``
is NOT_RUN until an actual execution record exists, BLOCKED when the
environment cannot satisfy requirements. Internal results are never
presented as external claims.
"""

from typing import Any, Dict, List


ADAPTER_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
ADAPTER_DESIGNED = "ADAPTER_DESIGNED"
ADAPTER_IMPLEMENTED = "ADAPTER_IMPLEMENTED"

EXEC_NOT_RUN = "NOT_RUN"
EXEC_BLOCKED = "BLOCKED"
EXEC_RUN = "RUN"
EXEC_PASSED = "PASSED"
EXEC_FAILED = "FAILED"


def _entry(benchmark: str, category: str, adapter: str, execution: str,
           environment: str, dataset: str, blocker: str = "") -> Dict[str, Any]:
    return {
        "benchmark": benchmark,
        "category": category,
        "adapter_status": adapter,
        "environment_requirements": environment,
        "dataset_status": dataset,
        "execution_status": execution,
        "last_run": "",
        "result": None,
        "blocker": blocker,
    }


EXTERNAL_BENCHMARKS: List[Dict[str, Any]] = [
    _entry("GAIA", "general assistant", ADAPTER_DESIGNED, EXEC_BLOCKED,
           "web browser + tool APIs", "not downloaded",
           "live web environment unavailable in this sandbox"),
    _entry("GAIA-2", "general assistant", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "web browser + tool APIs", "not downloaded",
           "adapter not designed yet"),
    _entry("AgentBench", "agent tasks", ADAPTER_DESIGNED, EXEC_BLOCKED,
           "docker + task environments", "not downloaded",
           "container task environments not configured"),
    _entry("AssistantBench", "web assistant", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "live web environment", "not downloaded",
           "adapter not designed yet"),
    _entry("SWE-Bench Verified", "software engineering", ADAPTER_DESIGNED, EXEC_BLOCKED,
           "docker + python repos", "not downloaded",
           "container dataset environment not configured"),
    _entry("SciCode", "scientific coding", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "scientific python stack", "not downloaded",
           "adapter not designed yet"),
    _entry("ScienceAgentBench", "science agent", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "domain tooling", "not downloaded",
           "adapter not designed yet"),
    _entry("CORE-Bench", "reproducibility", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "docker + papers", "not downloaded",
           "adapter not designed yet"),
    _entry("WebArena", "web navigation", ADAPTER_DESIGNED, EXEC_BLOCKED,
           "self-hosted web sites + browser", "not downloaded",
           "self-hosted arena not deployed"),
    _entry("VisualWebArena", "visual web", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "self-hosted sites + vision browser", "not downloaded",
           "adapter not designed yet"),
    _entry("OSWorld", "desktop control", ADAPTER_DESIGNED, EXEC_BLOCKED,
           "VM desktop environment", "not downloaded",
           "desktop VM unavailable"),
    _entry("Mind2Web", "web agent", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "offline snapshots + browser", "not downloaded",
           "adapter not designed yet"),
    _entry("tau-Bench", "tool dialogue", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "simulated APIs", "not downloaded",
           "adapter not designed yet"),
    _entry("WorkArena", "enterprise web", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "ServiceNow instance", "not downloaded",
           "adapter not designed yet"),
    _entry("AgentCompany", "organization tasks", ADAPTER_NOT_IMPLEMENTED, EXEC_NOT_RUN,
           "company simulation", "not downloaded",
           "adapter not designed yet"),
]


def registry_report() -> List[Dict[str, Any]]:
    """Honest snapshot: no benchmark claims without executions."""
    return [dict(entry) for entry in EXTERNAL_BENCHMARKS]


def executed_benchmarks() -> List[Dict[str, Any]]:
    return [e for e in EXTERNAL_BENCHMARKS
            if e["execution_status"] in (EXEC_RUN, EXEC_PASSED, EXEC_FAILED)]


def blocked_benchmarks() -> List[Dict[str, Any]]:
    return [e for e in EXTERNAL_BENCHMARKS
            if e["execution_status"] in (EXEC_BLOCKED, EXEC_NOT_RUN)]
