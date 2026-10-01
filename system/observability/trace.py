from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Structured Request Traces
Author: Heeran Paul
License: MIT
--------------------------------------------

Request -> Context -> Retrieval -> Model -> Planning -> Tool ->
Task -> Verification, threaded by shared correlation IDs.

``RequestTrace`` is the structured trace model; ``Tracer`` owns
traces and optionally mirrors stage events into an
``ObservabilityManager``. ``explain_*`` helpers answer the five
debugging questions with concise structured summaries built from
recorded metadata — never from private reasoning content.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STAGES = (
    "request",
    "context",
    "retrieval",
    "model_selection",
    "reasoning",
    "planning",
    "decisions",
    "tools",
    "agents",
    "verification",
    "final_result",
    # Stage 8 cognitive/autonomy stages (recorded via tracer.record).
    "cognitive_analysis",
    "plan_proposal",
    "plan_validation",
    "dependency_graph",
    "decision",
    "step",
    "capability_resolution",
    "ability",
    "permission",
    "execution",
    "observation",
    "replan",
    "reflection",
    "experience",
    "memory_write",
    "self_evaluation",
    "completion",
)


@dataclass
class RequestTrace:
    correlation_id: str
    request_id: str = ""
    task_id: str = ""
    execution_id: str = ""
    agent_id: str = ""
    stages: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    started_at: str = ""
    updated_at: str = ""

    def record_stage(self, stage: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        entry = {
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(data or {}),
        }
        self.stages.setdefault(stage, []).append(entry)
        self.updated_at = entry["timestamp"]
        return entry

    def as_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "stages": {k: list(v) for k, v in self.stages.items()},
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


class Tracer:
    """Own request traces; optionally mirror into ObservabilityManager."""

    def __init__(self, observability: Any = None):
        self.observability = observability
        self._traces: Dict[str, RequestTrace] = {}

    def start(
        self,
        correlation_id: str,
        request_id: str = "",
        task_id: str = "",
        execution_id: str = "",
        agent_id: str = "",
    ) -> RequestTrace:
        now = datetime.now(timezone.utc).isoformat()
        trace = RequestTrace(
            correlation_id=correlation_id,
            request_id=request_id,
            task_id=task_id,
            execution_id=execution_id,
            agent_id=agent_id,
            started_at=now,
            updated_at=now,
        )
        self._traces[correlation_id] = trace
        return trace

    def record(self, correlation_id: str, stage: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        trace = self._traces.get(correlation_id)
        if trace is None:
            trace = self.start(correlation_id)
        entry = trace.record_stage(stage, data)
        if self.observability is not None and hasattr(self.observability, "trace"):
            try:
                self.observability.trace(correlation_id, entry)
            except Exception:
                pass
        return entry

    def get(self, correlation_id: str) -> Optional[RequestTrace]:
        return self._traces.get(correlation_id)

    def snapshot(self) -> Dict[str, Any]:
        return {cid: trace.as_dict() for cid, trace in self._traces.items()}


# --------------------------------------------------
# Embedding / retrieval tracing (hashes + ids only, never raw text)
# --------------------------------------------------

def trace_embedding(
    tracer: Any,
    correlation_id: str,
    model_id: str = "",
    dimension: int = 0,
    batch_size: int = 1,
    latency_ms: float = 0.0,
    cache_hit: bool = False,
    fingerprints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record one embedding request. Safe no-op when tracer is None."""
    entry = {
        "model_id": model_id,
        "dimension": dimension,
        "batch_size": batch_size,
        "latency_ms": round(float(latency_ms), 3),
        "cache_hit": bool(cache_hit),
        "fingerprints": list(fingerprints or []),
    }
    if tracer is None:
        return entry
    try:
        return tracer.record(correlation_id, "embedding", entry)
    except Exception:
        return entry


def trace_retrieval(
    tracer: Any,
    correlation_id: str,
    strategy: str = "",
    hits: int = 0,
    latency_ms: float = 0.0,
    top_ids: Optional[List[str]] = None,
    degraded: bool = False,
) -> Dict[str, Any]:
    """Record one retrieval execution. Safe no-op when tracer is None."""
    entry = {
        "strategy": strategy,
        "hits": hits,
        "latency_ms": round(float(latency_ms), 3),
        "top_ids": list(top_ids or []),
        "degraded": bool(degraded),
    }
    if tracer is None:
        return entry
    try:
        return tracer.record(correlation_id, "retrieval", entry)
    except Exception:
        return entry


# --------------------------------------------------
# Learning decision tracing
# --------------------------------------------------

def trace_learning(
    tracer: Any,
    correlation_id: str,
    event: str,
    proposal_id: str = "",
    detail: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record intake/proposal/validation/promotion/rejection. None-safe."""
    entry = {
        "event": event,
        "proposal_id": proposal_id,
        "detail": dict(detail or {}),
    }
    if tracer is None:
        return entry
    try:
        return tracer.record(correlation_id, "learning", entry)
    except Exception:
        return entry


# --------------------------------------------------
# Autonomy tracing (plan -> capability -> tool -> verify -> replan)
# --------------------------------------------------

AUTONOMY_STAGES = (
    "plan_validation",
    "capability_resolution",
    "tool_selection",
    "permission",
    "execution",
    "verification",
    "replan",
)


def trace_autonomy(
    tracer: Any,
    correlation_id: str,
    stage: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record one autonomy stage. Unknown stages raise (no silent misfile)."""
    if stage not in AUTONOMY_STAGES:
        raise ValueError(f"unknown autonomy stage: {stage!r}")
    entry = dict(data or {})
    if tracer is None:
        return {"stage": stage, **entry}
    return tracer.record(correlation_id, stage, entry)


def explain_plan(validation: Any) -> Dict[str, Any]:
    data = dict(validation or {})
    problems = data.get("problems", []) or []
    return {
        "question": "Why this plan?",
        "answer": "plan valid" if data.get("valid") else f"plan invalid: {len(problems)} problem(s)",
        "evidence": {"metrics": data.get("metrics", {}),
                     "problems": [p.get("code") for p in problems if isinstance(p, dict)]},
    }


def explain_capability(selection: Any) -> Dict[str, Any]:
    data = selection.as_dict() if hasattr(selection, "as_dict") else dict(selection or {})
    selected = data.get("selected", {}) or {}
    return {
        "question": "Why this capability binding?",
        "answer": f"{selected.get('name')} covers {selected.get('covers')}",
        "evidence": {"coverage": data.get("coverage"), "rejected": data.get("rejected", [])},
    }


def explain_tool_choice(selection: Any) -> Dict[str, Any]:
    data = selection.as_dict() if hasattr(selection, "as_dict") else dict(selection or {})
    selected = data.get("selected", {}) or {}
    factors = selected.get("factors", {}) or {}
    top = max(factors, key=factors.get) if factors else "coverage"
    return {
        "question": "Why this tool?",
        "answer": f"{selected.get('kind')}:{selected.get('name')} (strongest factor: {top})",
        "evidence": {"factors": factors, "rejected": data.get("rejected", [])},
    }


def explain_agent_binding(selection: Any) -> Dict[str, Any]:
    data = selection.as_dict() if hasattr(selection, "as_dict") else dict(selection or {})
    selected = data.get("selected", {}) or {}
    if selected.get("kind") != "agent":
        return {"question": "Why this agent?", "answer": "no agent bound for this step",
                "evidence": {"selected_kind": selected.get("kind")}}
    return {
        "question": "Why this agent?",
        "answer": f"agent {selected.get('name')} provides {selected.get('covers')}",
        "evidence": {"factors": selected.get("factors", {})},
    }


def explain_tool_fallback(outcome: Any) -> Dict[str, Any]:
    data = dict(outcome or {})
    errors = data.get("errors", []) or []
    executor = data.get("executor") or {}
    return {
        "question": "Why fallback?",
        "answer": f"primary failed ({len(errors)} error(s)); used {executor.get('name') or 'none'}"
        if data.get("status") == "success" else f"all executors failed ({len(errors)} error(s))",
        "evidence": {"attempts": data.get("attempts"), "errors": errors},
    }


def explain_replan(report: Any) -> Dict[str, Any]:
    data = dict(report or {})
    return {
        "question": "Why replan?",
        "answer": f"{data.get('replans', 0)} replan(s); status {data.get('status')}",
        "evidence": {"failed": data.get("failed", []), "completed": data.get("completed", [])},
    }


def _resume_decision_answer(decision: Any) -> Dict[str, Any]:
    return decision.as_dict() if hasattr(decision, "as_dict") else dict(decision or {})


def explain_step_skipped(decision: Any) -> Dict[str, Any]:
    data = _resume_decision_answer(decision)
    return {
        "question": "Why was this step skipped?",
        "answer": f"{data.get('step_id')}: {data.get('reason', 'verified complete, no effects to repeat')}",
        "evidence": {"action": data.get("action"), "detail": data.get("detail", {})},
    }


def explain_step_replayed(decision: Any) -> Dict[str, Any]:
    data = _resume_decision_answer(decision)
    return {
        "question": "Why was this step replayed?",
        "answer": f"{data.get('step_id')}: {data.get('reason', 'not complete; replay after revalidation')}",
        "evidence": {"action": data.get("action"), "detail": data.get("detail", {})},
    }


def explain_compensation_required(decision: Any, outcome: Any = None) -> Dict[str, Any]:
    data = _resume_decision_answer(decision)
    result = dict(outcome or {})
    return {
        "question": "Why was compensation required?",
        "answer": f"{data.get('step_id')}: {data.get('reason', 'prior effects must be undone first')}",
        "evidence": {"action": data.get("action"), "compensation": result},
    }


def explain_resume_blocked(decision: Any) -> Dict[str, Any]:
    data = _resume_decision_answer(decision)
    return {
        "question": "Why was resume blocked?",
        "answer": f"{data.get('step_id')}: {data.get('reason', 'unsafe replay refused')}",
        "evidence": {"action": data.get("action"), "detail": data.get("detail", {})},
    }


# --------------------------------------------------
# Semantic capability tracing (fingerprints only, never raw content)
# --------------------------------------------------

SEMANTIC_EVENTS = (
    "semantic_requested",
    "model_selected",
    "proposal_received",
    "proposal_validated",
    "fallback",
)


def trace_semantic(
    tracer: Any,
    correlation_id: str,
    event: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record one semantic-inference event. Unknown events raise."""
    if event not in SEMANTIC_EVENTS:
        raise ValueError(f"unknown semantic event: {event!r}")
    entry = dict(data or {})
    if tracer is None:
        return {"event": event, **entry}
    try:
        return tracer.record(correlation_id, f"semantic_{event}", entry)
    except Exception:
        return {"event": event, **entry}


def explain_semantic_proposal(resolution: Any) -> Dict[str, Any]:
    data = resolution.as_dict() if hasattr(resolution, "as_dict") else dict(resolution or {})
    return {
        "question": "Why was this capability proposed semantically?",
        "answer": f"{len(data.get('semantic', []))} semantic candidate(s) in {data.get('mode')} mode",
        "evidence": {"model": data.get("model_id"), "fallback_used": data.get("fallback_used"),
                     "latency_ms": data.get("latency_ms")},
    }


def explain_capability_accepted(entry: Any) -> Dict[str, Any]:
    data = dict(entry or {})
    return {
        "question": "Why was this capability accepted?",
        "answer": f"{data.get('name')} passed registry, health, and policy checks",
        "evidence": {"confidence": data.get("confidence"), "source": data.get("source")},
    }


def explain_capability_rejected(entry: Any) -> Dict[str, Any]:
    data = dict(entry or {})
    rejection = data.get("rejection", {}) or {}
    return {
        "question": "Why was this capability rejected?",
        "answer": f"{data.get('name')}: {rejection.get('code', 'unknown')}",
        "evidence": {"rejection": rejection, "source": data.get("source")},
    }


def explain_deterministic_fallback(resolution: Any) -> Dict[str, Any]:
    data = resolution.as_dict() if hasattr(resolution, "as_dict") else dict(resolution or {})
    return {
        "question": "Why deterministic fallback?",
        "answer": "; ".join(data.get("errors", [])) or "; ".join(data.get("warnings", [])) or "no reason recorded",
        "evidence": {"fallback_used": data.get("fallback_used"), "errors": data.get("errors", [])},
    }


def explain_semantic_disabled(resolution: Any) -> Dict[str, Any]:
    data = resolution.as_dict() if hasattr(resolution, "as_dict") else dict(resolution or {})
    return {
        "question": "Why was semantic inference disabled?",
        "answer": "; ".join(data.get("warnings", [])) or "semantic proposer not enabled",
        "evidence": {"mode": data.get("mode")},
    }


def explain_shadow_difference(resolution: Any) -> Dict[str, Any]:
    data = resolution.as_dict() if hasattr(resolution, "as_dict") else dict(resolution or {})
    comparison = (data.get("validation", {}) or {}).get("shadow_comparison", {})
    return {
        "question": "How did shadow semantic differ?",
        "answer": f"agree={comparison.get('agree', [])} semantic-only={comparison.get('only_semantic', [])}",
        "evidence": {"comparison": comparison},
    }


# --------------------------------------------------
# Diagnostic explanations (structured, no reasoning traces)
# --------------------------------------------------

def explain_model_selection(decision: Any) -> Dict[str, Any]:
    data = decision.as_dict() if hasattr(decision, "as_dict") else dict(decision or {})
    return {
        "question": "Why was this model selected?",
        "answer": str(data.get("reason", "no routing decision recorded")),
        "evidence": {
            "model": data.get("model"),
            "adapter": data.get("adapter_name"),
            "task_type": data.get("task_type"),
            "fallback_chain": data.get("fallback_chain", []),
        },
    }


def explain_memory_retrieval(context_payload: Any) -> Dict[str, Any]:
    data = dict(context_payload or {})
    items = data.get("items", []) or []
    by_source: Dict[str, int] = {}
    for item in items:
        by_source[str(item.get("source", "unknown"))] = by_source.get(str(item.get("source", "unknown")), 0) + 1
    return {
        "question": "Why was this memory retrieved?",
        "answer": f"{len(items)} context items from {sorted(by_source)} (correlation {data.get('correlation_id')})",
        "evidence": {"sources": by_source, "diagnostics": data.get("diagnostics", [])},
    }


def explain_tool_selection(task: Any) -> Dict[str, Any]:
    data = dict(task or {})
    return {
        "question": "Why was this tool selected?",
        "answer": f"tool={data.get('selected_tool')} agent={data.get('selected_agent')} model={data.get('selected_model')}",
        "evidence": {"required_permissions": data.get("required_permissions", []), "plan": data.get("plan", [])},
    }


def explain_retry(task: Any) -> Dict[str, Any]:
    data = dict(task or {})
    history = data.get("history") or []
    reasons = [str(h.get("reason", "")) for h in history if isinstance(h, dict) and h.get("reason")]
    return {
        "question": "Why did this task retry?",
        "answer": reasons[-1] if reasons else f"retry_count={data.get('retry_count', 0)}",
        "evidence": {"retry_count": data.get("retry_count", 0), "last_error": data.get("last_error")},
    }


def explain_verification_failure(task: Any) -> Dict[str, Any]:
    data = dict(task or {})
    verification = data.get("verification") or {}
    return {
        "question": "Why did verification fail?",
        "answer": f"state={data.get('verification_state')} expected={verification.get('expected')} observed={verification.get('observed')}",
        "evidence": {"verification": verification, "last_error": data.get("last_error")},
    }
