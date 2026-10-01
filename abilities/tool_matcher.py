from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Tool Matcher
Author: Heeran Paul
License: MIT
--------------------------------------------

Matches required capabilities to ranked tool/agent candidates and
executes with explicit fallback. Separation is strict:

ModelRouter -> MODEL · ToolMatcher -> TOOL · AgentManager -> AGENT ·
Orchestrator -> EXECUTION coordination.

A tool lacking required coverage is never selected; permissions are
pre-checked for ranking AND re-enforced at execution (the matcher
cannot override policy).
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from abilities.tool_health import ToolHealthMonitor, ToolPerformanceTracker
from cognition.capabilities.capability import coerce_all

_HEALTH_WEIGHT = {"READY": 1.0, "DEGRADED": 0.5, "LOADING": 0.4,
                  "AVAILABLE": 0.9, "UNAVAILABLE": 0.0, "FAILED": 0.0}


def _structured_failure_text(result: object) -> str | None:
    """Honest structured failures must trigger fallback, never count as success.

    Abilities return ``{"status": "failed", "error": ...}`` on failure;
    only ``{"status": "success", ...}`` may proceed to verification.
    """
    if not isinstance(result, dict):
        return None
    status = str(result.get("status", "")).lower()
    if status in ("failed", "error", "pending"):
        detail = result.get("error") or f"ability reported status '{status}'"
        return str(detail)[:300]
    if result.get("error") and status != "success":
        return str(result.get("error"))[:300]
    return None


class ToolMatchError(RuntimeError):
    def __init__(self, message: str, code: str = "TOOL_MATCH_ERROR", step_id: str = ""):
        super().__init__(message)
        self.code = code
        self.step_id = step_id


class _StructuredFailure(RuntimeError):
    """Internal: ability returned an honest failure dict (fallback trigger)."""


@dataclass
class ToolCandidate:
    kind: str  # tool | agent
    name: str
    covers: List[str] = field(default_factory=list)
    total: float = 0.0
    factors: Dict[str, float] = field(default_factory=dict)
    permission: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "name": self.name, "covers": list(self.covers),
                "total": round(self.total, 4),
                "factors": {k: round(v, 4) for k, v in self.factors.items()},
                "permission": {"allowed": self.permission.get("allowed"), "risk": self.permission.get("risk")}}


@dataclass
class ToolSelection:
    step_id: str
    selected: ToolCandidate
    candidates: List[ToolCandidate] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    coverage: str = "FULL"  # FULL | PARTIAL | NO_COVERAGE

    def as_dict(self) -> Dict[str, Any]:
        return {"step_id": self.step_id, "selected": self.selected.as_dict(),
                "candidates": [c.as_dict() for c in self.candidates],
                "rejected": list(self.rejected), "coverage": self.coverage}


class ToolMatcher:
    """Rank and select capability providers for plan steps."""

    def __init__(
        self,
        ability_manager=None,
        policy_manager=None,
        agent_manager=None,
        capability_registry=None,
        health_monitor: Optional[ToolHealthMonitor] = None,
        environment: str = "default",
    ):
        self.abilities = ability_manager
        self.policy = policy_manager
        self.agents = agent_manager
        self.registry = capability_registry
        self.health = health_monitor or ToolHealthMonitor()
        self.environment = environment

    # --------------------------------------------------
    def _live_providers(self, capability: str) -> List[Dict[str, Any]]:
        providers = self.registry.providers_for(capability, self.environment) if self.registry else []
        live = []
        for provider in providers:
            if provider.kind == "tool":
                status = self.health.check_tool(provider.name, self.abilities)
            else:
                status = self.health.check_agent(provider.name, self.agents)
            if status.get("state", "").upper() in ("READY", "DEGRADED"):
                live.append({"provider": provider, "health": status})
        return live

    def _permission(self, capability: str, risk: str = "LOW") -> Dict[str, Any]:
        if self.policy is None:
            return {"allowed": True, "risk": risk, "reason": "no policy bound"}
        try:
            return self.policy.evaluate(capability, {"risk": risk}, actor="tool-matcher")
        except Exception as exc:
            return {"allowed": False, "risk": risk, "reason": str(exc)[:160]}

    def match(self, step: Dict[str, Any], allow_partial: bool = False,
              preferred: Optional[Dict[str, str]] = None) -> ToolSelection:
        """Select the best healthy, policy-approved provider.

        ``preferred`` (CAPABILITY -> ability, from past successful
        experience) adds a small ranking boost to that provider only —
        it never skips health, permission, or coverage checks.
        """
        step_id = str(step.get("step_id", "step-?"))
        try:
            required = [c.value for c in coerce_all(step.get("required_capabilities", []) or [])]
        except ValueError as exc:
            raise ToolMatchError(f"step {step_id} declares unknown capability: {exc}",
                                 "UNKNOWN_CAPABILITY", step_id)
        if not required:
            raise ToolMatchError(f"step {step_id} declares no capabilities", "NO_CAPABILITY_DECLARED", step_id)
        risk = str(step.get("risk", "LOW"))

        per_cap = {cap: self._live_providers(cap) for cap in required}
        missing = [cap for cap, live in per_cap.items() if not live]
        if missing and not allow_partial:
            raise ToolMatchError(f"step {step_id} has no healthy provider for {missing}",
                                 "NO_HEALTHY_PROVIDER", step_id)

        # Candidate executors: single providers covering the most caps.
        by_executor: Dict[str, Dict[str, Any]] = {}
        for cap, live in per_cap.items():
            for entry in live:
                provider = entry["provider"]
                key = f"{provider.kind}:{provider.name}"
                slot = by_executor.setdefault(key, {"provider": provider, "covers": [], "health": entry["health"]})
                slot["covers"].append(cap)
        if not by_executor:
            raise ToolMatchError(f"step {step_id}: no coverage", "NO_CAPABILITY_COVERAGE", step_id)

        scored: List[ToolCandidate] = []
        rejected: List[Dict[str, Any]] = []
        for key, slot in by_executor.items():
            provider, covers = slot["provider"], slot["covers"]
            permission = self._permission(covers[0], risk)
            if not permission.get("allowed", True):
                rejected.append({"kind": provider.kind, "name": provider.name,
                                 "reason": f"permission denied for {covers[0]}"})
                continue
            coverage_ratio = len(covers) / len(required)
            health_w = _HEALTH_WEIGHT.get(slot["health"].get("state", "LOADING"), 0.0)
            reliability = self.health.tracker.stats_for(provider.name).success_rate()
            total = 0.55 * coverage_ratio + 0.20 * health_w + 0.15 * reliability + 0.10 * (1.0 if provider.kind == "tool" else 0.8)
            factors: Dict[str, float] = {"coverage": coverage_ratio, "health": health_w,
                                         "reliability": reliability}
            # Experience hint: prefer the previously successful provider
            # for a required capability (revalidated above; never overrides).
            if preferred:
                for cap in covers:
                    if str(preferred.get(str(cap).upper(), "")).lower() == str(provider.name).lower():
                        total += 0.15
                        factors["experience"] = 0.15
                        break
            scored.append(ToolCandidate(provider.kind, provider.name, covers, total,
                                        factors, permission))
        if not scored:
            raise ToolMatchError(f"step {step_id}: all candidates permission-denied",
                                 "PERMISSION_DENIED", step_id)
        scored.sort(key=lambda c: c.total, reverse=True)
        best = scored[0]
        coverage = "FULL" if len(best.covers) == len(required) else "PARTIAL"
        if coverage == "PARTIAL" and not allow_partial:
            raise ToolMatchError(
                f"step {step_id}: partial coverage only ({best.covers} of {required}); "
                "decompose the step or allow_partial", "PARTIAL_COVERAGE", step_id)
        return ToolSelection(step_id, best, scored, rejected, coverage)

    # --------------------------------------------------
    def execute_candidate(self, candidate: ToolCandidate, step: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Any:
        """Execute via AbilityManager (tools) or AgentManager (agents).

        Permissions re-enforced live by AbilityManager.execute; agents
        are pre-checked here since AgentManager has no policy gate.
        Mapping payloads merge into the agent task envelope; scalar
        payloads travel as ``{"input": payload}`` / positional input.
        """
        if candidate.kind == "agent":
            if self.agents is None:
                raise ToolMatchError(f"no agent manager for {candidate.name}", "NO_AGENT_MANAGER", candidate.name)
            for cap in candidate.covers:
                decision = self._permission(cap, str(step.get("risk", "LOW")))
                if not decision.get("allowed", True):
                    raise ToolMatchError(f"permission denied for agent {candidate.name} ({cap})",
                                         "PERMISSION_DENIED", str(step.get("step_id", "")))
            envelope: Dict[str, Any] = {"step": step}
            if isinstance(payload, dict):
                envelope.update(payload)
            elif payload is not None:
                envelope["input"] = payload
            return self.agents.execute_task(candidate.name, envelope)
        if self.abilities is None:
            raise ToolMatchError(f"no ability manager for {candidate.name}", "NO_ABILITY_MANAGER", candidate.name)
        # Canonical capabilities travel with the call so execution is
        # authorized per capability, not just per tool name.
        # Empty payloads fall back to the step description so abilities
        # receive the actual task text ({} must never reach eval/parse).
        if isinstance(payload, dict) and payload:
            task_input: Any = payload
        elif isinstance(payload, str) and payload.strip():
            task_input = payload
        else:
            task_input = step.get("description", "")
        import logging as _logging
        _logging.getLogger("HERCULE.RequestLifecycle").info(
            "CAPABILITY→SELECTED ABILITY caps=%s ability=%s step=%s",
            list(step.get("required_capabilities", []) or []), candidate.name,
            str(step.get("step_id", "")))
        return self.abilities.execute(candidate.name, task_input,
                                      capabilities=list(step.get("required_capabilities", []) or []),
                                      environment=self.environment)

    def execute_with_fallback(self, selection: ToolSelection, step: Dict[str, Any],
                              payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """PRIMARY -> SECONDARY -> ... -> CLEAR FAILURE with classification.

        Destructive steps (HIGH risk, retry_destructive False) are never
        blindly retried on the same executor.
        """
        from evaluation.failures import classify_failure

        step_id = selection.step_id
        retry_policy = step.get("retry_policy", {}) or {}
        max_retries = int(retry_policy.get("max_retries", 1))
        retry_destructive = bool(retry_policy.get("retry_destructive", False))
        destructive = str(step.get("risk", "LOW")).upper() == "HIGH"
        errors: List[str] = []
        attempts = 0
        for candidate in selection.candidates:
            # Same-executor retry only when safe.
            tries = 1 + (max_retries if not (destructive and not retry_destructive) else 0)
            for _ in range(tries):
                attempts += 1
                started = time.perf_counter()
                try:
                    result = self.execute_candidate(candidate, step, payload)
                    failure_text = _structured_failure_text(result)
                    if failure_text is not None:
                        raise _StructuredFailure(failure_text)
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    self.health.tracker.record(candidate.name, True, latency_ms)
                    self.health.note_success(candidate.name)
                    return {"status": "success", "executor": candidate.as_dict(),
                            "result": result, "attempts": attempts, "errors": errors}
                except Exception as exc:
                    latency_ms = (time.perf_counter() - started) * 1000.0
                    self.health.tracker.record(candidate.name, False, latency_ms)
                    self.health.note_failure(candidate.name)
                    failure = classify_failure(exc)
                    errors.append(f"{candidate.kind}:{candidate.name}: [{failure.code}] {exc}")
                    if not failure.retryable or (destructive and not retry_destructive):
                        break  # next candidate, never blind retry
        return {"status": "failed", "executor": None, "result": None,
                "attempts": attempts, "errors": errors}
