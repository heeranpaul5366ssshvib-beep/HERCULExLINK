from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Hybrid Capability Resolution
Author: Heeran Paul
License: MIT
--------------------------------------------

ONE authoritative resolution layer:

DETERMINISTIC SIGNALS + SEMANTIC PROPOSALS
-> NORMALIZATION -> DEDUPLICATION -> CONFLICT ANALYSIS
-> DETERMINISTIC VALIDATOR -> FINAL CAPABILITIES

Modes: DETERMINISTIC | SEMANTIC_OPTIONAL | HYBRID | SEMANTIC_REQUIRED
| SHADOW. Default production behavior is SEMANTIC_OPTIONAL: the
deterministic set always runs, semantic candidates are validated,
and semantic failure falls back silently-safe.

This layer authorizes NOTHING. Every accepted capability still passes
registry + health + policy at the plan validator and again at
execution. Confidence influences ranking/diagnostics only.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from cognition.capabilities.capability import Capability, coerce_capability
from cognition.capabilities.inference import _RULES, infer_capabilities
from cognition.capabilities.proposal import (
    CapabilityProposal,
    ProposalError,
    ProposalSource,
)
from cognition.capabilities.semantic import fingerprint
from cognition.capabilities.vocabulary import CAPABILITY_DEPENDENCIES, normalize_name


class HybridMode(str, Enum):
    DETERMINISTIC = "deterministic"
    SEMANTIC_OPTIONAL = "semantic_optional"
    HYBRID = "hybrid"
    SEMANTIC_REQUIRED = "semantic_required"
    SHADOW = "shadow"


class ResolutionError(RuntimeError):
    """Structured resolution failure with a machine-readable code."""

    def __init__(self, message: str, code: str = "INFERENCE_FAILED"):
        super().__init__(message)
        self.code = code


@dataclass
class HybridResolution:
    """Structured outcome of one resolution (never an authorization)."""

    final: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)
    deterministic: List[Dict[str, Any]] = field(default_factory=list)
    semantic: List[Dict[str, Any]] = field(default_factory=list)
    accepted: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False
    shadow: bool = False
    mode: str = "semantic_optional"
    model_id: str = ""
    latency_ms: float = 0.0
    validation: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "final": list(self.final), "optional": list(self.optional),
            "deterministic": list(self.deterministic), "semantic": list(self.semantic),
            "accepted": list(self.accepted), "rejected": list(self.rejected),
            "conflicts": list(self.conflicts), "fallback_used": self.fallback_used,
            "shadow": self.shadow, "mode": self.mode, "model_id": self.model_id,
            "latency_ms": round(self.latency_ms, 3), "validation": dict(self.validation),
            "warnings": list(self.warnings), "errors": list(self.errors),
        }


def _phrases_for(capability_name: str) -> List[str]:
    try:
        cap = coerce_capability(capability_name)
    except ValueError:
        return []
    return [phrase for c, phrases in _RULES if c == cap for phrase in phrases]


def _supported_by(text: str, capability_name: str) -> bool:
    """True when the goal text itself mentions the capability (by name,
    alias, or rule phrase) — i.e. the proposal is grounded in user intent
    rather than floating on model output alone."""
    from cognition.capabilities.vocabulary import ALIASES

    lowered = (text or "").lower()
    if not lowered.strip():
        return True  # nothing to check against
    if capability_name.lower() in lowered:
        return True
    for alias, cap in ALIASES.items():
        if cap.value == capability_name and alias in lowered:
            return True
    return any(phrase in lowered for phrase in _phrases_for(capability_name))


def negated_by_backstop(text: str, capability_name: str) -> bool:
    """Deterministic negation backstop: every textual evidence phrase
    for this capability appears negated in the task. The model can never
    override this — negated requirements stay out of required caps."""
    phrases = _phrases_for(capability_name)
    if not phrases:
        return False
    lowered = text.lower()
    hits = [p for p in phrases if p in lowered]
    if not hits:
        return False
    import re
    negations = ("do not", "don't", "dont", "never", "without", "not ", "n't ", "refuse to", "avoid")
    for sentence in re.split(r"[.!?;\n]+", lowered):
        for phrase in hits:
            if phrase in sentence and not any(m in sentence.split(phrase)[0] for m in negations):
                return False  # at least one unnegated mention
    return True


def to_proposals(names: List[Any], source: ProposalSource, confidence: float = 1.0,
                 required: bool = True) -> List[CapabilityProposal]:
    out = []
    for name in names:
        cap = name if isinstance(name, Capability) else coerce_capability(str(name))
        out.append(CapabilityProposal(name=cap.value, confidence=confidence, source=source,
                                      explanation=f"{source.value} signal", required=required))
    return out


class ProposalCache:
    """Cache for semantic proposal SETS only — never for validation or
    authorization outcomes, which are recomputed on every resolution."""

    def __init__(self, maxsize: int = 256, version: str = "1"):
        self.maxsize = maxsize
        self.version = version
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self.hits = 0
        self.misses = 0

    def key(self, task: str, model_id: str, allowed: List[str], min_confidence: float) -> str:
        digest = hashlib.sha256("|".join([
            task, model_id, ",".join(sorted(allowed)), str(min_confidence), self.version,
        ]).encode("utf-8")).hexdigest()[:16]
        return digest

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        hit = self._store.get(key)
        if hit is None:
            self.misses += 1
            return None
        self.hits += 1
        return [dict(p) for p in hit]

    def put(self, key: str, proposals: List[Dict[str, Any]]) -> None:
        if len(self._store) >= self.maxsize:
            self._store.pop(next(iter(self._store)))
        self._store[key] = [dict(p) for p in proposals]


def resolve_capabilities(
    step: Any,
    context: str = "",
    untrusted_content: str = "",
    registry=None,
    policy=None,
    ability_manager=None,
    agent_manager=None,
    environment: str = "default",
    mode: HybridMode = HybridMode.SEMANTIC_OPTIONAL,
    proposer=None,
    explicit_capabilities: Optional[List[str]] = None,
    proposal_cache: Optional[ProposalCache] = None,
    tracer=None,
    correlation_id: str = "",
) -> HybridResolution:
    """Resolve one step's capabilities through the hybrid pipeline."""
    if isinstance(mode, str):
        try:
            mode = HybridMode(mode)
        except ValueError:
            raise ResolutionError(f"unknown hybrid mode: {mode}", "INFERENCE_FAILED")
    started = time.perf_counter()
    resolution = HybridResolution(mode=mode.value)
    text = step.get("description", "") if isinstance(step, dict) else str(step)
    trusted_step = not isinstance(step, dict) or step.get("trusted", True)
    _emit(tracer, correlation_id, "semantic_requested",
          {"mode": resolution.mode, "task": fingerprint(text)})

    # 1. Deterministic signals (always run).
    det_names = [c.value for c in infer_capabilities(step)]
    det_proposals = to_proposals(det_names, ProposalSource.KEYWORD)
    explicit: List[CapabilityProposal] = []
    for name in explicit_capabilities or []:
        try:
            normalized = normalize_name(str(name))
            cap = coerce_capability(normalized)
            explicit.append(CapabilityProposal(name=cap.value, confidence=1.0,
                                               source=ProposalSource.EXPLICIT_USER,
                                               explanation="explicit user request"))
        except ValueError:
            explicit.append(CapabilityProposal(name=str(name).strip().upper(), confidence=1.0,
                                               source=ProposalSource.EXPLICIT_USER,
                                               explanation="explicit user request", known=False))
    resolution.deterministic = [p.as_dict() for p in det_proposals + explicit]

    # 2. Semantic candidates.
    semantic: List[CapabilityProposal] = []
    use_semantic = mode in (HybridMode.SEMANTIC_OPTIONAL, HybridMode.HYBRID,
                            HybridMode.SEMANTIC_REQUIRED, HybridMode.SHADOW)
    if use_semantic and proposer is not None and getattr(proposer, "enabled", True):
        cache_key = ""
        if proposal_cache is not None:
            model_hint = getattr(getattr(proposer, "model", None), "default_model", "")
            cache_key = proposal_cache.key(text, model_hint,
                                            list(getattr(proposer, "allowed_capabilities", []) or []),
                                            float(getattr(proposer, "min_confidence", 0.5)))
            cached = proposal_cache.get(cache_key)
            if cached is not None:
                resolution.warnings.append("proposal cache hit")
                semantic = [CapabilityProposal(
                    name=p["name"], confidence=p.get("confidence", 0.5),
                    source=ProposalSource(p.get("source", "semantic_model")),
                    explanation=p.get("explanation", ""), required=p.get("required", True),
                    condition=p.get("condition", ""),
                    depends_on=p.get("depends_on", [])) for p in cached]
        if not semantic:
            try:
                outcome = proposer.propose(task=text, context=context, untrusted_content=untrusted_content,
                                           deterministic_proposals=[])
                resolution.model_id = outcome.model_id
                resolution.latency_ms = outcome.latency_ms
                resolution.warnings.extend(outcome.warnings)
                resolution.errors.extend(outcome.errors)
                if outcome.fallback_used:
                    resolution.fallback_used = True
                    if mode == HybridMode.SEMANTIC_REQUIRED:
                        raise ResolutionError(
                            f"semantic required but inference fell back: {outcome.errors}",
                            "SEMANTIC_UNAVAILABLE")
                semantic = [p for p in outcome.proposals if p.source == ProposalSource.SEMANTIC_MODEL]
                if proposal_cache is not None and cache_key and not outcome.fallback_used:
                    proposal_cache.put(cache_key, [p.as_dict() for p in semantic])
            except ProposalError as exc:
                if mode == HybridMode.SEMANTIC_REQUIRED:
                    raise ResolutionError(str(exc), "SEMANTIC_UNAVAILABLE")
                resolution.fallback_used = True
                resolution.errors.append(f"SEMANTIC_UNAVAILABLE: {exc}"[:200])
            except ResolutionError:
                raise
            except Exception as exc:
                if mode == HybridMode.SEMANTIC_REQUIRED:
                    raise ResolutionError(f"semantic inference failed: {exc}"[:200], "INFERENCE_FAILED")
                resolution.fallback_used = True
                resolution.errors.append(f"INFERENCE_FAILED: {exc}"[:200])
    elif use_semantic and proposer is None:
        resolution.warnings.append("no proposer bound; deterministic only")
        resolution.fallback_used = True
    resolution.semantic = [p.as_dict() for p in semantic]

    # 3. Normalization + deduplication + conflict analysis.
    candidates = _merge(det_proposals, explicit, semantic)
    resolution.conflicts = _conflicts(det_proposals, explicit, semantic)

    # 4. Deterministic validator gate (FINAL authority).
    accepted, rejected = _validate(
        candidates, text, trusted_step, registry, policy,
        ability_manager, agent_manager, environment, resolution.warnings,
        untrusted_content=untrusted_content)
    resolution.accepted = [p.as_dict() for p in accepted]
    resolution.rejected = [p.as_dict() for p in rejected]
    resolution.validation = {
        "accepted": len(accepted), "rejected": len(rejected),
        "checked": len(candidates),
    }

    # 5. Final sets (+ shadow comparison).
    required = [p for p in accepted if p.required]
    optional = [p for p in accepted if not p.required]
    if mode == HybridMode.SHADOW:
        resolution.shadow = True
        det_names_set = {p.name for p in det_proposals + explicit}
        resolution.final = [p.name for p in required if p.name in det_names_set]
        resolution.optional = [p.name for p in optional if p.name in det_names_set]
        from cognition.capabilities.semantic import compare_proposals
        resolution.validation["shadow_comparison"] = compare_proposals(
            det_proposals + explicit, semantic)
        resolution.warnings.append("shadow mode: deterministic authoritative")
    else:
        resolution.final = [p.name for p in required]
        resolution.optional = [p.name for p in optional]
    resolution.latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    _emit(tracer, correlation_id, "proposal_received",
          {"semantic": len(resolution.semantic), "model": resolution.model_id,
           "fallback": resolution.fallback_used})
    _emit(tracer, correlation_id, "proposal_validated",
          {"accepted": [p["name"] for p in resolution.accepted],
           "rejected": [(p["name"], (p.get("rejection") or {}).get("code")) for p in resolution.rejected]})
    if resolution.fallback_used:
        _emit(tracer, correlation_id, "fallback", {"errors": resolution.errors})
    return resolution


def _emit(tracer, correlation_id, event, data) -> None:
    if tracer is None or not correlation_id:
        return
    try:
        from system.observability.trace import trace_semantic
        trace_semantic(tracer, correlation_id, event, data)
    except Exception:
        pass


def _merge(det: List[CapabilityProposal], explicit: List[CapabilityProposal],
           semantic: List[CapabilityProposal]) -> List[CapabilityProposal]:
    """Explicit > deterministic > semantic precedence; required wins on merge."""
    merged: Dict[str, CapabilityProposal] = {}
    order = [(semantic, 0), (det, 1), (explicit, 2)]
    rank = {id(p): r for group, r in order for p in group}
    for group in (semantic, det, explicit):
        for proposal in group:
            if (proposal.condition and proposal.required
                    and proposal.source != ProposalSource.EXPLICIT_USER):
                # Conditional requirements are represented, never forced
                # into unconditional plans (explicit user intent keeps
                # its flag and still passes validation + policy).
                proposal.required = False
            existing = merged.get(proposal.name)
            if existing is None:
                merged[proposal.name] = proposal
            else:
                if rank[id(proposal)] >= rank[id(existing)]:
                    proposal.confidence = max(proposal.confidence, existing.confidence)
                    proposal.required = proposal.required or existing.required
                    proposal.depends_on = sorted(set(proposal.depends_on) | set(existing.depends_on))
                    if existing.condition and existing.condition not in (proposal.condition or ""):
                        proposal.condition = (proposal.condition + "; " + existing.condition).strip("; ")
                    if not proposal.explanation:
                        proposal.explanation = existing.explanation
                    merged[proposal.name] = proposal
                else:
                    existing.confidence = max(existing.confidence, proposal.confidence)
                    existing.required = existing.required or proposal.required
                    existing.depends_on = sorted(set(existing.depends_on) | set(proposal.depends_on))
    return list(merged.values())


def _conflicts(det: List[CapabilityProposal], explicit: List[CapabilityProposal],
               semantic: List[CapabilityProposal]) -> List[Dict[str, Any]]:
    notes = []
    by_name: Dict[str, List[CapabilityProposal]] = {}
    for proposal in list(det) + list(explicit) + list(semantic):
        by_name.setdefault(proposal.name, []).append(proposal)
    for name, group in by_name.items():
        sources = sorted({p.source.value for p in group})
        if len(sources) > 1:
            notes.append({"capability": name, "kind": "multi_source", "sources": sources})
        if any(p.condition for p in group):
            notes.append({"capability": name, "kind": "conditional",
                          "conditions": [p.condition for p in group if p.condition]})
    return notes


def _validate(candidates: List[CapabilityProposal], text: str, trusted_step: bool,
              registry, policy, ability_manager, agent_manager, environment: str,
              warnings: List[str], untrusted_content: str = "") -> tuple:
    """The gate: registry existence, env support, provider health,
    negation backstop, untrusted-content grounding, policy
    compatibility, dependency edges."""
    accepted: List[CapabilityProposal] = []
    rejected: List[Dict[str, Any]] = []

    def refuse(proposal: CapabilityProposal, code: str, reason: str):
        proposal.rejection = {"code": code, "reason": reason}
        rejected.append(proposal)

    for proposal in candidates:
        name = normalize_name(proposal.name)
        try:
            cap = coerce_capability(name)
            proposal.name = cap.value
            proposal.known = True
        except ValueError:
            proposal.known = False
            refuse(proposal, "UNKNOWN_CAPABILITY", f"not in canonical registry: {proposal.name}")
            continue
        # Negation backstop: the model cannot override negated intent
        # (explicit user requests still pass — the user said it).
        if (proposal.source == ProposalSource.SEMANTIC_MODEL and trusted_step
                and negated_by_backstop(text, cap.value)):
            refuse(proposal, "NEGATED_REQUIREMENT", f"task negates {cap.value}; deterministic backstop")
            continue
        if not trusted_step and proposal.source == ProposalSource.SEMANTIC_MODEL and proposal.required:
            proposal.required = False
            warnings.append(f"untrusted step: {cap.value} demoted to optional")
        # Untrusted-content grounding: a semantic proposal supported ONLY
        # by untrusted content (not by the user goal) cannot become a
        # required capability — prompt separation plus this backstop.
        if (proposal.source == ProposalSource.SEMANTIC_MODEL and proposal.required
                and untrusted_content and not _supported_by(text, cap.value)
                and _supported_by(untrusted_content, cap.value)):
            proposal.required = False
            warnings.append(f"untrusted grounding: {cap.value} demoted to optional")
        # Dependency edges: validated, never invented.
        for dep in list(proposal.depends_on):
            try:
                coerce_capability(dep)
            except ValueError:
                proposal.depends_on.remove(dep)
                warnings.append(f"impossible dependency dropped: {dep}")
        if registry is None:
            accepted.append(proposal)
            continue
        providers = registry.providers_for(cap.value, environment)
        if not providers:
            refuse(proposal, "UNSUPPORTED_CAPABILITY", f"no provider for {cap.value} in {environment}")
            continue
        healthy = False
        for provider in providers:
            try:
                if provider.kind == "tool":
                    state = ""
                    if ability_manager is not None and hasattr(ability_manager, "get"):
                        ability = ability_manager.get(provider.name)
                        state = "READY" if ability is not None and getattr(ability, "enabled", True) else "UNAVAILABLE"
                    else:
                        state = "READY"
                else:
                    state = "READY"
                    if agent_manager is not None and hasattr(agent_manager, "get_agent"):
                        agent = agent_manager.get_agent(provider.name)
                        raw = str(getattr(getattr(agent, "state", None), "name", "READY")) if agent else "MISSING"
                        state = "READY" if raw.upper() not in ("ERROR", "TERMINATED", "MISSING", "OFFLINE") else "UNAVAILABLE"
                if state == "READY":
                    healthy = True
                    break
            except Exception:
                continue
        if not healthy:
            refuse(proposal, "UNHEALTHY_CAPABILITY", f"no healthy provider for {cap.value}")
            continue
        if policy is not None:
            try:
                decision = policy.evaluate(cap.value, {"risk": "LOW"}, actor="hybrid-validator")
                if not decision.get("allowed", True):
                    refuse(proposal, "POLICY_DENIED", f"policy denies {cap.value}")
                    continue
            except Exception as exc:
                refuse(proposal, "POLICY_ERROR", str(exc)[:160])
                continue
        accepted.append(proposal)
    accepted_names = {p.name for p in accepted}
    for proposal in accepted:
        try:
            expected = CAPABILITY_DEPENDENCIES.get(coerce_capability(proposal.name), [])
        except ValueError:
            expected = []
        missing = [d.value for d in expected if d.value not in accepted_names]
        if missing:
            warnings.append(f"advisory: {proposal.name} usually pairs with {missing}")
    return accepted, rejected
