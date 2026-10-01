from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Resume Planner & Compensation
Author: Heeran Paul
License: MIT
--------------------------------------------

Safe resume for interrupted tasks. Distinguishes VERIFIED COMPLETE /
VERIFIED NOT COMPLETE / UNKNOWN per step, decides SKIP / REPLAY /
COMPENSATE / BLOCK from effect class + verification + current policy,
health, and environment — then executes compensations explicitly.

Never assumes completed steps are repeatable; never claims
exactly-once (see describe_semantics).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cognition.capabilities.capability import coerce_capability
from cognition.capabilities.effects import (
    EffectClass,
    claim_allowed,
    coerce_effect,
    default_effect_for,
)

SKIP = "SKIP"
REPLAY = "REPLAY"
COMPENSATE = "COMPENSATE"
BLOCK = "BLOCK"


@dataclass
class ResumeDecision:
    step_id: str
    action: str
    reason: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"step_id": self.step_id, "action": self.action,
                "reason": self.reason, "detail": dict(self.detail)}


@dataclass
class ResumePlan:
    task_id: str
    decisions: List[ResumeDecision] = field(default_factory=list)
    environment: str = "default"
    environment_changed: bool = False

    @property
    def blocked(self) -> bool:
        return any(d.action == BLOCK for d in self.decisions)

    @property
    def reset_steps(self) -> List[str]:
        """Completed states to reopen so the loop replays them."""
        return [d.step_id for d in self.decisions if d.action in (REPLAY, COMPENSATE)]

    def as_dict(self) -> Dict[str, Any]:
        return {"task_id": self.task_id, "blocked": self.blocked,
                "environment": self.environment, "environment_changed": self.environment_changed,
                "decisions": [d.as_dict() for d in self.decisions]}


class ResumePlanner:
    """Decide and execute safe resume for one task."""

    def __init__(self, task_manager=None, matcher=None, environment: str = "default"):
        self.tasks = task_manager
        self.matcher = matcher
        self.environment = environment

    # --------------------------------------------------
    def _stored_states(self, task_id: str) -> Dict[str, Any]:
        try:
            states = (self.tasks.get(task_id).get("metadata", {}) or {}).get("capability_states", {})
            return states if isinstance(states, dict) else {}  # malformed checkpoint: treat as no state
        except Exception:
            return {}

    def _revalidate(self, step: Dict[str, Any]) -> Optional[str]:
        """Current policy/health check. Returns blocking reason or None."""
        if self.matcher is None:
            return None
        caps = step.get("required_capabilities", []) or []
        policy = getattr(self.matcher, "policy", None)
        if policy is not None:
            for cap in caps:
                try:
                    decision = policy.evaluate(str(cap), {"risk": str(step.get("risk", "LOW"))},
                                               actor="resume-validator")
                    if not decision.get("allowed", True):
                        return f"permission now denied for {cap}"
                except Exception as exc:
                    return f"policy error for {cap}: {exc}"[:160]
        registry = getattr(self.matcher, "registry", None)
        if registry is not None:
            for cap in caps:
                try:
                    providers = registry.providers_for(cap, self.environment)
                    healthy = []
                    for provider in providers:
                        if provider.kind == "tool":
                            state = self.matcher.health.check_tool(
                                provider.name, self.matcher.abilities).get("state", "").upper()
                        else:
                            state = self.matcher.health.check_agent(
                                provider.name, self.matcher.agents).get("state", "").upper()
                        if state in ("READY", "DEGRADED"):
                            healthy.append(provider)
                    if not healthy:
                        return f"no healthy provider now for {cap}"
                except Exception as exc:
                    return f"capability error for {cap}: {exc}"[:160]
        return None

    # --------------------------------------------------
    def plan(self, task_id: str, plan_steps: List[Dict[str, Any]]) -> ResumePlan:
        states = self._stored_states(task_id)
        try:
            stored_env = (self.tasks.get(task_id).get("metadata", {}) or {}).get("resume_environment", "")
        except Exception:
            stored_env = ""
        plan = ResumePlan(task_id=task_id, environment=self.environment,
                          environment_changed=bool(stored_env) and stored_env != self.environment)
        self._env_changed = plan.environment_changed
        for step in plan_steps:
            sid = str(step.get("step_id", ""))
            plan.decisions.append(self._decide(task_id, step, sid, states.get(sid)))
        self._env_changed = False
        return plan

    def _decide(self, task_id: str, step: Dict[str, Any], sid: str, stored: Optional[Dict[str, Any]]) -> ResumeDecision:
        caps = step.get("required_capabilities", []) or []
        try:
            declared = coerce_effect(step.get("effect", "EFFECTFUL"))
        except ValueError:
            return ResumeDecision(sid, BLOCK, "malformed effect class", {"effect": step.get("effect")})
        try:
            capability_default = default_effect_for([coerce_capability(c) for c in caps])
        except ValueError as exc:
            return ResumeDecision(sid, BLOCK, f"unknown capability: {exc}", {})
        if not claim_allowed(declared, capability_default):
            return ResumeDecision(sid, BLOCK,
                                  f"false idempotency: declared {declared.value} weaker than {capability_default.value}",
                                  {"declared": declared.value, "default": capability_default.value})
        # verification may be stored as None (attempt recorded without
        # verification yet); treat missing data as unverified, never crash.
        verified = bool(((stored or {}).get("verification") or {}).get("passed"))
        status = str((stored or {}).get("status", "")).lower() if stored else ""

        if not stored:
            return self._gate(step, sid, REPLAY, "never attempted; fresh execution after revalidation")
        if status == "completed" and verified:
            return self._verified_complete(step, sid, declared)
        if status in ("failed-verification", "failed", "running", "pending") or not verified:
            return self._not_complete(step, sid, declared, status or "unknown")

    def _gate(self, step: Dict[str, Any], sid: str, action: str, reason: str) -> ResumeDecision:
        problem = self._revalidate(step)
        if problem:
            return ResumeDecision(sid, BLOCK, problem, {"wanted": action})
        return ResumeDecision(sid, action, reason, {"revalidated": True})

    def _verified_complete(self, step: Dict[str, Any], sid: str, declared: EffectClass) -> ResumeDecision:
        if declared == EffectClass.READ_ONLY:
            return ResumeDecision(sid, SKIP, "read-only and verified complete; no effects to repeat", {})
        if declared == EffectClass.IDEMPOTENT:
            if step.get("state_check"):
                return ResumeDecision(sid, REPLAY, "idempotent with state check; check decides skip vs replay",
                                      {"state_check": True})
            return self._gate(step, sid, REPLAY, "idempotent replay is safe after revalidation")
        if declared == EffectClass.COMPENSATABLE:
            comp = step.get("compensation")
            if not comp:
                return ResumeDecision(sid, BLOCK, "compensatable step lacks declared compensation", {})
            return self._gate(step, sid, COMPENSATE, "run declared compensation, then replay original")
        if declared == EffectClass.NON_RESUMABLE:
            return ResumeDecision(sid, BLOCK, "non-resumable step already attempted; restart required", {})
        # EFFECTFUL verified-complete: replay would duplicate effects.
        if str(step.get("resume_policy", "default")) == "replay-ok":
            return self._gate(step, sid, REPLAY, "explicit replay-ok resume policy")
        if getattr(self, "_env_changed", False):
            return ResumeDecision(sid, BLOCK, "environment changed since verified completion", {})
        return ResumeDecision(sid, BLOCK, "effectful verified-complete; replay would duplicate effects", {})

    def _not_complete(self, step: Dict[str, Any], sid: str, declared: EffectClass, status: str) -> ResumeDecision:
        if declared == EffectClass.NON_RESUMABLE and status not in ("", "pending"):
            return ResumeDecision(sid, BLOCK, f"non-resumable step in state {status}; restart required", {})
        if declared in (EffectClass.EFFECTFUL, EffectClass.COMPENSATABLE) and status in ("running",):
            # Interrupted mid-execution: unknown whether effects landed.
            if declared == EffectClass.COMPENSATABLE and step.get("compensation"):
                return self._gate(step, sid, COMPENSATE, "unknown mid-run state; compensate then replay")
            if str(step.get("resume_policy", "default")) == "replay-ok":
                return self._gate(step, sid, REPLAY, "explicit replay-ok resume policy")
            return ResumeDecision(sid, BLOCK, f"unknown mid-run state for {declared.value}; explicit policy required",
                                  {"status": status})
        return self._gate(step, sid, REPLAY, f"verified not complete ({status}); replay after revalidation")

    # --------------------------------------------------
    def run_state_check(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a read-only state check; pass means effects present."""
        check = step.get("state_check") or {}
        if not check:
            return {"ran": False, "passed": False, "detail": "no state check declared"}
        if self.matcher is None or self.matcher.abilities is None:
            return {"ran": False, "passed": False, "detail": "no ability manager"}
        capability = str(check.get("capability", ""))
        try:
            providers = self.matcher.registry.providers_for(capability, self.environment)
        except Exception as exc:
            return {"ran": False, "passed": False, "detail": str(exc)[:160]}
        read_providers = [p for p in providers if p.kind == "tool"]
        if not read_providers:
            return {"ran": False, "passed": False, "detail": f"no tool provider for check {capability}"}
        name = read_providers[0].name
        try:
            result = self.matcher.abilities.execute(name, check.get("input", ""),
                                                    capabilities=[capability])
        except Exception as exc:
            return {"ran": True, "passed": False, "detail": f"check execution failed: {exc}"[:200]}
        text = str(result.get("content", result) if isinstance(result, dict) else result)
        expect = str(check.get("expect", ""))
        passed = (expect in text) if expect else bool(text.strip())
        return {"ran": True, "passed": passed, "detail": "state present" if passed else "state absent"}

    def execute_compensation(self, step: Dict[str, Any], correlation_id: str = "") -> Dict[str, Any]:
        """Validate (capability+permission) and run the declared compensation."""
        from abilities.tool_matcher import ToolMatchError
        from orchestrator.step_verifier import verify_step

        comp = step.get("compensation") or {}
        if not comp or not comp.get("capability"):
            return {"status": "blocked", "detail": "missing compensation declaration"}
        if self.matcher is None:
            return {"status": "blocked", "detail": "no matcher bound"}
        action = {"step_id": f"{step.get('step_id', 'step')}-compensate",
                  "description": str(comp.get("description", "compensation")),
                  "required_capabilities": [str(comp["capability"])],
                  "risk": step.get("risk", "HIGH"),
                  "verification_criteria": ["compensation verified"],
                  "retry_policy": {"max_retries": 0, "retry_destructive": False}}
        try:
            selection = self.matcher.match(action)
        except ToolMatchError as exc:
            return {"status": "blocked", "detail": str(exc), "code": exc.code}
        outcome = self.matcher.execute_with_fallback(selection, action)
        if outcome["status"] != "success":
            return {"status": "failed", "detail": "; ".join(outcome["errors"])}
        verdict = verify_step(action, outcome)
        if not verdict.get("passed"):
            return {"status": "failed", "detail": verdict.get("detail", "")}
        return {"status": "compensated", "detail": verdict.get("detail", "")}
