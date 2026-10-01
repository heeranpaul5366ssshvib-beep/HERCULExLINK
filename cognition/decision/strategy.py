from __future__ import annotations
"""
HERCULE AI Operating System
Phase 5: Decision Intelligence — Candidate Strategy Scoring

New strategy-candidate schema + deterministic scoring used by the
DecisionEngine candidate layer. Hides nothing behind the model:

* the model may PROPOSE candidate strategies
* this module does the canonical VALIDATION + SCORING + RANKING
* execution remains downstream of policy/security/verification

All candidates must pass plan validation before the decision engine
can consider them (no bypassing validation).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from cognition.capabilities.capability import Capability, coerce_capability

# Re-export the decision-gate validator (authoritative definition in
# validate.py) so the Phase-5 facade imports stay stable across modules.
try:
    from .validate import validate_candidate
except Exception:  # pragma: no cover - defensive; validate_candidate always present
    validate_candidate = None  # type: ignore


# ---------------------------------------------------------------------------
# Strategy candidate schema (§2 of the Phase 5 spec)
# ---------------------------------------------------------------------------

VALID_RISKS = ("LOW", "MEDIUM", "HIGH")


def _risk_rank(risk: str) -> int:
    try:
        return VALID_RISKS.index(str(risk).upper())
    except ValueError:
        return len(VALID_RISKS)


def normalize_risk(value: str) -> str:
    r = str(value or "LOW").upper()
    return r if r in VALID_RISKS else "MEDIUM"


@dataclass
class CandidateStrategy:
    """One validated candidate strategy for a goal.

    Every field the model suggests is advisory; the decision engine
    recomputes the canonical score. Invalid candidates are discarded
    before scoring (the decision engine never chooses through invalid
    strategies).
    """

    strategy_id: str
    goal: str
    steps: List[Dict[str, Any]]
    required_capabilities: List[str] = field(default_factory=list)
    required_abilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    estimated_cost: float = 1.0
    estimated_latency_s: float = 30.0
    risk: str = "LOW"
    verification_difficulty: str = "STANDARD"
    expected_success: float = 0.5
    experience_support: float = 0.0
    source: str = "deterministic"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "goal": self.goal,
            "steps": list(self.steps),
            "required_capabilities": list(self.required_capabilities),
            "required_abilities": list(self.required_abilities),
            "dependencies": list(self.dependencies),
            "estimated_cost": float(self.estimated_cost),
            "estimated_latency_s": float(self.estimated_latency_s),
            "risk": str(self.risk),
            "verification_difficulty": str(self.verification_difficulty),
            "expected_success": float(self.expected_success),
            "experience_support": float(self.experience_support),
            "source": str(self.source),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CandidateStrategy":
        data = dict(data or {})
        caps: List[str] = []
        for c in (data.get("required_capabilities") or []):
            try:
                caps.append(coerce_capability(c).value)
            except ValueError:
                caps.append(str(c).upper())
        return cls(
            strategy_id=str(data.get("strategy_id", "") or "s-1"),
            goal=str(data.get("goal", "") or ""),
            steps=list(data.get("steps") or []),
            required_capabilities=caps,
            required_abilities=[str(a) for a in (data.get("required_abilities") or [])],
            dependencies=[str(d) for d in (data.get("dependencies") or [])],
            estimated_cost=float(data.get("estimated_cost", 1.0) or 1.0),
            estimated_latency_s=float(data.get("estimated_latency_s", 30.0) or 30.0),
            risk=normalize_risk(data.get("risk", "LOW")),
            verification_difficulty=str(data.get("verification_difficulty", "STANDARD")),
            expected_success=float(max(0.0, min(1.0, data.get("expected_success", 0.5) or 0.5))),
            experience_support=float(max(0.0, min(1.0, data.get("experience_support", 0.0) or 0.0))),
            source=str(data.get("source", "deterministic")),
            metadata=dict(data.get("metadata") or {}),
        )

    # Lightweight internal contract: every executable step needs a goal
    # and at least one declared capability. This is NOT the full plan
    # validation (which requires registry/policy/verification) — it is the
    # minimal sanity gate that prevents obviously malformed model proposals
    # from reaching the scoring path.
    def internal_contract_ok(self) -> bool:
        if not self.steps:
            return False
        if not str(self.goal).strip():
            return False
        for step in self.steps:
            if not str(step.get("goal", step.get("description", step.get("objective", ""))) or "").strip():
                return False
            if not step.get("required_capabilities"):
                return False
        return True


def _world_state_fit(candidate: CandidateStrategy,
                     world_state: Optional[Dict[str, Any]]) -> float:
    """World-model alignment bonus/penalty for one candidate (§7).

    Deterministic, advisory, bounded to [-0.4, +0.4]:

    - A strategy whose steps "reuse"/"inspect"/"read" an application or
      file that the world model reports as currently existing gets a small
      positive alignment.
    - A strategy that proposes to "launch"/"start"/"open"/"create" something
      the world model already reports as present gets a small penalty
      (duplicate work; inspect-first is usually safer and cheaper).
    - Unknown/stale world state contributes 0 — never authority. Downstream
      validation and verification still gate everything the strategy does.
    """
    if not world_state:
        return 0.0
    text = " ".join(
        str(s.get("goal", s.get("description", "")))
        for s in (candidate.steps or [])
    ).lower()
    if not text:
        return 0.0
    apps = [str(a).lower() for a in (world_state.get("applications") or [])]
    files = 0
    try:
        files = int((world_state.get("by_type") or {}).get("file", 0) or 0)
    except Exception:
        files = 0
    reuse_bonus = 0.0
    if apps:
        for app in apps:
            if app and app in text and any(
                    v in text for v in ("reuse", "existing", "use the", "running")):
                reuse_bonus = 0.2
                break
    duplicate_penalty = 0.0
    launch_words = ("launch", "start ", "open ", "install ", "create the app")
    if apps and any(app in text for app in apps) and any(v in text for v in launch_words):
        duplicate_penalty = -0.3
    inspect_first = 0.0
    if files and any(v in text for v in ("read the existing", "inspect the", "check the existing",
                                         "read ", "inspect ")):
        inspect_first = 0.1
    overwrite_penalty = 0.0
    if files and any(v in text for v in ("overwrite", "delete the", "remove the")):
        overwrite_penalty = -0.2
    total = reuse_bonus + duplicate_penalty + inspect_first + overwrite_penalty
    return max(-0.4, min(0.4, total))


# ---------------------------------------------------------------------------
# Experience-backed capability success lookup
# ---------------------------------------------------------------------------

def build_experience_stats(
    experiences: Sequence[Any],
    *,
    cap_weight: float = 1.0,
    ability_weight: float = 0.6,
) -> Dict[str, float]:
    """Collapse a sequence of experience records into per-capability success.

    Returns {CAPABILITY: 0.0..1.0}. Only verified successes count as 1.0;
    partials get 0.5; failures get 0.0. Ability-level signals are folded in
    with a lower weight so a capability can be preferred even when the exact
    ability name differs.
    """
    cap_scores: Dict[str, List[float]] = {}
    ab_scores: Dict[str, List[float]] = {}
    for exp in (experiences or []):
        get = (lambda k, d="": exp.get(k, d)) if isinstance(exp, dict) else (lambda k, d="": getattr(exp, k, d))
        caps = [str(c).upper() for c in (get("capabilities", []) or [])]
        abils = [str(a) for a in (get("abilities", []) or [])]
        succ = float(get("success", 0.0) or 0.0)
        succ = max(0.0, min(1.0, succ))
        for c in caps:
            cap_scores.setdefault(c, []).append(succ)
        for a in abils:
            ab_scores.setdefault(a.upper(), []).append(succ)
    out: Dict[str, float] = {}
    for cap, values in cap_scores.items():
        mean = sum(values) / len(values)
        out[cap] = round(mean * cap_weight, 3)
    for ab, values in ab_scores.items():
        mean = sum(values) / len(values)
        out[ab] = round(max(out.get(ab, 0.0), mean * ability_weight), 3)
    return out


# ---------------------------------------------------------------------------
# Deterministic scoring (§3/§4 of the spec)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    "expected_success": 3.0,
    "experience_support": 2.0,
    "capability_fit": 2.0,
    "environment_fit": 1.5,
    "verification_quality": 3.0,
    "risk": -2.0,
    "latency": -1.0,
    "cost": -0.5,
    "verification_difficulty_penalty": -1.5,
}

# Budget penalty (§18) is applied by decide_strategies ONLY to candidates
# whose estimated latency exceeds time_budget_s; it is not part of the
# default weight set so it never penalizes in-budget strategies.
BUDGET_PENALTY_WEIGHT = -2.0


def score_strategy(
    candidate: CandidateStrategy,
    *,
    experience_stats: Optional[Dict[str, float]] = None,
    available_abilities: Optional[Sequence[str]] = None,
    available_capabilities: Optional[Sequence[str]] = None,
    environment: str = "default",
    world_fit: float = 0.0,
    user_constraints: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None,
    world_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministic score for one validated candidate strategy.

    Scoring components (all configurable via ``weights``; see
    DEFAULT_WEIGHTS and §4 of the Phase 5 spec):

    - expected_success: blend of the candidate's declared success
      expectation and per-capability verified experience (§3.1/§6)
    - experience_support: prior verified success on the same capability
      set (advisory; downstream validation still applies) (§3.2/§6)
    - capability_fit: share of required capabilities/abilities that are
      actually available in this environment (§3.3/§3.4)
    - environment_fit: environment match + world-model fit (§3.9/§7)
    - verification_quality: strength of the candidate's verification
      story (§3.8/§9)
    - risk / latency / cost: penalties (§3.5-§3.7)
    - verification_difficulty_penalty: extra penalty for weak
      verification on executable actions (§9)

    The LLM never computes this score; the model may only propose the
    candidate. Higher is better. Invalid candidates are not scored by
    the caller; this function assumes ``candidate.internal_contract_ok()``
    has passed.
    """
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items()})

    components: Dict[str, float] = {k: 0.0 for k in w}

    # --- success (§3.1) ---
    exp_lookup = dict(experience_stats or {})
    cap_hits = sum(1 for c in candidate.required_capabilities if float(exp_lookup.get(str(c).upper(), 0.0)) >= 0.5)
    denom = max(1, len(candidate.required_capabilities))
    success_from_exp = cap_hits / denom
    success = float(candidate.expected_success) * 0.5 + success_from_exp * 0.5
    success = max(0.0, min(1.0, success))
    components["expected_success"] = w["expected_success"] * success

    # --- experience support (§3.2 / §6) ---
    exp_support = float(candidate.experience_support)
    # boost when the exact capability set has a prior verified success
    capset = frozenset(str(c).upper() for c in candidate.required_capabilities)
    match_bonus = 0.0
    if exp_lookup:
        for c in capset:
            if float(exp_lookup.get(c, 0.0)) >= 0.9:
                match_bonus += 0.25
        match_bonus = min(0.5, match_bonus)
    exp_value = min(1.0, exp_support + match_bonus)
    components["experience_support"] = w["experience_support"] * exp_value

    # --- capability fit (§3.3/§3.4) ---
    # An explicitly-empty availability set means nothing is available
    # (fit 0); an absent/None set means the caller does not know (fit 1,
    # neutral — downstream validation remains authoritative).
    if available_capabilities is None:
        cap_fit = 1.0
    elif not capset:
        cap_fit = 1.0
    else:
        avail = {str(c).upper() for c in (available_capabilities or [])}
        cap_fit = len(capset & avail) / len(capset)
    if available_abilities is None or not candidate.required_abilities:
        ab_fit = 1.0
    else:
        avail_ab = {str(a).upper() for a in (available_abilities or [])}
        needed_ab = {str(a).upper() for a in candidate.required_abilities}
        ab_fit = len(needed_ab & avail_ab) / len(needed_ab)
    fit = 0.6 * cap_fit + 0.4 * ab_fit
    components["capability_fit"] = w["capability_fit"] * fit

    # --- environment fit (§3.9 / §7) ---
    env = str(environment or "default")
    if env and env.lower() != "default":
        # when a non-default environment is in play, prefer candidates that
        # declare a match; otherwise small penalty
        declared_env = str((candidate.metadata or {}).get("environment", "")).lower()
        env_fit = 1.0 if declared_env == env.lower() else 0.6
    else:
        env_fit = 1.0
    # World-model fit (§7): prefer strategies aligned with actual current
    # state (e.g. reuse an already-running application instead of launching
    # a second one; read/inspect an existing file before overwriting). The
    # world model is context only — it never grants authority and stale
    # state must still be re-verified downstream before execution.
    world_component = _world_state_fit(candidate, world_state)
    env_value = max(0.0, min(1.0, env_fit + max(world_fit, 0.0) + world_component))
    components["environment_fit"] = w["environment_fit"] * env_value

    # --- verification quality (§3.8 / §9) ---
    vdiff = str(candidate.verification_difficulty).upper()
    vmap = {"NONE": 0.0, "MINIMAL": 0.4, "STANDARD": 0.7, "STRONG": 1.0, "COMPREHENSIVE": 1.0}
    verification_quality = vmap.get(vdiff, 0.5)
    components["verification_quality"] = w["verification_quality"] * verification_quality

    # --- risk (§3.5 / §8) ---
    risk_rank = _risk_rank(candidate.risk)
    risk_value = risk_rank / max(1, len(VALID_RISKS) - 1)
    components["risk"] = w["risk"] * risk_value

    # --- latency (§3.6 / §10) ---
    lat = float(candidate.estimated_latency_s or 0.0)
    lat_value = min(1.0, lat / 120.0)
    components["latency"] = w["latency"] * lat_value

    # --- cost (§3.7) ---
    cost_value = float(candidate.estimated_cost or 1.0)
    components["cost"] = w["cost"] * cost_value

    # --- verification difficulty penalty (§9) ---
    # STRONG/COMPREHENSIVE verification stories earn a small bonus here
    # (they make verification_quality reachable and honest); weak stories
    # are penalized. "NONE" on an executable action is heavily penalized.
    vdiff_penalty = {"NONE": 1.0, "MINIMAL": 0.5, "STANDARD": 0.0, "STRONG": -0.3, "COMPREHENSIVE": -0.4}.get(
        vdiff, 0.0
    )
    components["verification_difficulty_penalty"] = w["verification_difficulty_penalty"] * vdiff_penalty

    # --- budget penalty (§18, applied by decide_strategies when the
    #     candidate's estimated latency exceeds time_budget_s) ---
    components["budget_penalty"] = w.get("budget_penalty", 0.0)  # 0 unless flagged over-budget

    score = sum(components.values())
    score = round(score, 3)

    reason_parts: List[str] = []
    reason_parts.append(f"success={success:.2f}")
    reason_parts.append(f"exp={exp_value:.2f}")
    reason_parts.append(f"fit={fit:.2f}")
    reason_parts.append(f"risk={candidate.risk}")
    reason_parts.append(f"vdiff={vdiff}")
    reason_parts.append(f"lat={lat:.0f}s")
    reason_parts.append(f"cost={cost_value:.1f}")
    reason = ", ".join(reason_parts)

    return {"score": score, "components": components, "reason": reason}


# ---------------------------------------------------------------------------
# Dominance (§5)
# ---------------------------------------------------------------------------

@dataclass
class DominanceResult:
    dominated: bool
    reason: str
    by: Optional[str] = None


def find_dominated(
    candidates: Sequence[CandidateStrategy],
    scores: Dict[str, float],
) -> Dict[str, DominanceResult]:
    """Basic Pareto-style dominance among valid candidates (§5).

    Candidate A is dominated by candidate B when B is not worse in any
    first-class dimension (risk, verification, cost, latency), strictly
    better in at least one of them, and at least as good on the
    authoritative score. Dominated candidates are recorded with a reason
    and skipped during selection (unless every candidate is dominated).
    """
    items = list(candidates)
    results: Dict[str, DominanceResult] = {}
    for a in items:
        a_score = scores.get(a.strategy_id, float("-inf"))
        dominated_by: Optional[str] = None
        for b in items:
            if b is a:
                continue
            b_score = scores.get(b.strategy_id, float("-inf"))
            if b_score < a_score - 1e-6:
                continue  # B scores strictly worse — cannot dominate A
            a_risk = _risk_rank(a.risk)
            b_risk = _risk_rank(b.risk)
            a_verif = _vdiff_rank(a.verification_difficulty)
            b_verif = _vdiff_rank(b.verification_difficulty)
            a_cost = float(a.estimated_cost)
            b_cost = float(b.estimated_cost)
            a_lat = float(a.estimated_latency_s)
            b_lat = float(b.estimated_latency_s)
            # B must not be worse on any first-class dimension...
            if b_risk > a_risk or b_verif < a_verif:
                continue
            if b_cost > a_cost + 1e-6 or b_lat > a_lat + 1e-6:
                continue
            # ...and strictly better on at least one (§5: safer, faster,
            # equally capable, equally verifiable ⇒ A should not be chosen).
            strictly_better = (
                b_risk < a_risk or b_verif > a_verif
                or b_cost < a_cost - 1e-6 or b_lat < a_lat - 1e-6
            )
            if strictly_better:
                dominated_by = b.strategy_id
                break
        results[a.strategy_id] = DominanceResult(
            dominated=dominated_by is not None,
            reason=(
                f"dominated by {dominated_by} (safer/faster/equally verifiable at least as good)"
                if dominated_by
                else "not dominated"
            ),
            by=dominated_by,
        )
    return results


def _vdiff_rank(vdiff: str) -> int:
    try:
        return ["NONE", "MINIMAL", "STANDARD", "STRONG", "COMPREHENSIVE"].index(
            str(vdiff).upper()
        )
    except ValueError:
        return 2


# ---------------------------------------------------------------------------
# Decision — rank + select (§3/§5/§11)
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    goal: str
    candidates: List[CandidateStrategy]
    valid_candidates: List[CandidateStrategy]
    rejected_candidates: List[Dict[str, Any]]
    scores: Dict[str, float]
    selected: Optional[CandidateStrategy]
    selection_reason: str
    dominated: Dict[str, DominanceResult]
    weights: Dict[str, float]
    decision_time_ms: float
    user_constraint_applied: bool
    over_budget_ids: List[str] = field(default_factory=list)


def decide_strategies(
    goal: str,
    candidates: Sequence[CandidateStrategy],
    *,
    experience_stats: Optional[Dict[str, float]] = None,
    available_abilities: Optional[Sequence[str]] = None,
    available_capabilities: Optional[Sequence[str]] = None,
    environment: str = "default",
    world_fit: float = 0.0,
    user_constraints: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None,
    tie_break: Optional[str] = None,
    decision_time_ms: Optional[float] = None,
    world_state: Optional[Dict[str, Any]] = None,
    time_budget_s: Optional[float] = None,
) -> DecisionRecord:
    """Authoritative strategy selection among VALID candidates.

    Steps:
    1. discard candidates failing the internal contract
    2. score each remaining candidate deterministically (with world-model
       fit §7 and, when ``time_budget_s`` is set, a documented over-budget
       penalty on estimated latency §18)
    3. apply explicit-user-constraint priority (§10) if present
    4. remove dominated strategies (§5)
    5. rank by score with documented tie-break (§11):
       safer → more verifiable → previously verified → simpler → faster
    """
    import time as _time

    t0 = _time.perf_counter()
    w = dict(DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items()})
    tie = str(tie_break or "safety,verification,experience,simplicity,speed")

    candidates = list(candidates or [])
    all_ids = {str(c.strategy_id) for c in candidates}

    # 1. contract gate.
    valid: List[CandidateStrategy] = []
    rejected: List[Dict[str, Any]] = []
    for c in candidates:
        if not c.internal_contract_ok():
            rejected.append({"strategy_id": c.strategy_id, "reason": "invalid candidate (internal contract)"})
            continue
        valid.append(c)

    # 2. deterministic scoring (world-model fit §7 + budget §18).
    scores: Dict[str, float] = {}
    over_budget: List[str] = []
    for c in valid:
        extra: Dict[str, float] = {}
        if time_budget_s is not None:
            try:
                if float(c.estimated_latency_s) > float(time_budget_s):
                    extra["budget_penalty"] = BUDGET_PENALTY_WEIGHT
                    over_budget.append(c.strategy_id)
            except (TypeError, ValueError):
                pass
        merged = dict(w)
        merged.update(extra)
        r = score_strategy(
            c,
            experience_stats=experience_stats,
            available_abilities=available_abilities,
            available_capabilities=available_capabilities,
            environment=environment,
            world_fit=world_fit,
            user_constraints=user_constraints,
            weights=merged,
            world_state=world_state,
        )
        scores[c.strategy_id] = r["score"]

    # 3. explicit user constraint priority (§10): when the user explicitly
    #    constrains the choice, honor it over pure score optimization.
    constraint_applied = False
    selected: Optional[CandidateStrategy] = None
    if user_constraints:
        constrained = _filter_by_user_constraints(valid, user_constraints)
        if constrained:
            valid = constrained
            constraint_applied = True

    # 4. dominance removal (§5): dominated strategies are recorded but still
    #    kept in ``valid`` for observability — selection skips them.
    dominated = find_dominated(valid, scores)

    # 5. ranking with documented tie-break.
    def sort_key(c: CandidateStrategy):
        sid = c.strategy_id
        score = scores.get(sid, float("-inf"))
        # tie-break order (§11): safer, more verifiable, previously verified,
        # simpler, faster.
        risk = _risk_rank(c.risk)
        verif = _vdiff_rank(c.verification_difficulty)
        exp = float(c.experience_support)
        cost = float(c.estimated_cost)
        lat = float(c.estimated_latency_s)
        return (
            -score,
            risk,
            -verif,
            -exp,
            cost,
            lat,
        )

    ranked = sorted(valid, key=sort_key)

    # skip dominated unless every valid candidate is dominated (then pick the
    # best of the dominated set honestly and record why).
    nondominated = [c for c in ranked if not dominated.get(c.strategy_id, DominanceResult(False, "")).dominated]
    if nondominated:
        selected = nondominated[0]
    elif ranked:
        selected = ranked[0]

    # selection reason.
    reason_parts: List[str] = []
    if constraint_applied:
        reason_parts.append("user constraint honored")
    if selected is None:
        reason_parts.append("no valid candidate")
    else:
        reason_parts.append(f"selected {selected.strategy_id}")
        reason_parts.append(f"score={scores.get(selected.strategy_id, 0.0):.2f}")
        if dominated.get(selected.strategy_id, DominanceResult(False, "")).dominated:
            reason_parts.append("dominant over remaining")
        else:
            reason_parts.append(
                "best on tie-break: " + tie
            )
        for c in ranked[:3]:
            reason_parts.append(f"{c.strategy_id}={scores.get(c.strategy_id, 0.0):.2f}")
    if over_budget:
        reason_parts.append("over-budget: " + ",".join(over_budget))
    decision_time_ms = float(decision_time_ms or (1000.0 * (_time.perf_counter() - t0)))
    return DecisionRecord(
        goal=goal,
        candidates=candidates,
        valid_candidates=valid,
        rejected_candidates=rejected,
        scores=scores,
        selected=selected,
        selection_reason="; ".join(reason_parts),
        dominated=dominated,
        weights=w,
        decision_time_ms=decision_time_ms,
        user_constraint_applied=constraint_applied,
        over_budget_ids=over_budget,
    )


def _filter_by_user_constraints(
    candidates: List[CandidateStrategy],
    constraints: Dict[str, Any],
) -> List[CandidateStrategy]:
    """Return candidates honoring explicit user constraints.

    Supported constraint keys (honored strictly; anything unknown is ignored
    so the model cannot smuggle a bypass):

    * ``require_strategy_id`` — exact match
    * ``require_risk`` — candidate risk must be <= this
    * ``require_verification`` — candidate verification_difficulty must be >= this
    * ``disallow_risk`` — candidate risk must be lower than this
    * ``prefer_cost_le`` — keep candidates whose cost is <= this
    """
    if not constraints:
        return candidates
    allowed: List[CandidateStrategy] = []
    require_id = str(constraints.get("require_strategy_id", "")).strip().upper()
    require_risk = str(constraints.get("require_risk", "")).upper()
    require_verification = str(constraints.get("require_verification", "")).upper()
    disallow_risk = str(constraints.get("disallow_risk", "")).upper()
    prefer_cost_le = constraints.get("prefer_cost_le")
    try:
        prefer_cost_le = float(prefer_cost_le) if prefer_cost_le is not None else None
    except (TypeError, ValueError):
        prefer_cost_le = None
    for c in candidates:
        if require_id and str(c.strategy_id).upper() != require_id:
            continue
        if require_risk and _risk_rank(c.risk) > _risk_rank(require_risk):
            continue
        if require_verification and _vdiff_rank(c.verification_difficulty) < _vdiff_rank(require_verification):
            continue
        if disallow_risk and _risk_rank(c.risk) >= _risk_rank(disallow_risk):
            continue
        if prefer_cost_le is not None and float(c.estimated_cost) > prefer_cost_le:
            continue
        allowed.append(c)
    return allowed
