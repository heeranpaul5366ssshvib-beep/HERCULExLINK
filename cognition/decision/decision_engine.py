from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Decision Engine (Phase 5 facade)
Author: Heeran Paul
License: MIT
--------------------------------------------

Authoritative strategy selection lives in cognition.decision.strategy
(score_strategy, decide_strategies, find_dominated, validate_candidate).

This class is the frozen, phase-stable *facade* that existing callers
(brain.plan_with_policy, tests) still reference. It delegates to the
Phase 5 candidate layer and preserves the legacy API surface so nothing
else is broken.
"""

from typing import Any, Dict, List, Optional, Sequence

from cognition.capabilities.capability import Capability
from cognition.decision.strategy import (
    CandidateStrategy,
    DecisionRecord,
    build_experience_stats,
    decide_strategies,
    find_dominated,
    normalize_risk,
    score_strategy,
    validate_candidate,
)


class DecisionEngine:
    """
    Responsible for selecting the best action
    from available options.

    Phase 5 (Decision Intelligence):
    - choose() selects from scored options (degenerate case)
    - compare_plans() now scores Phase-5 CandidateStrategy candidates
      deterministically via the decision-intelligence layer
    """

    def __init__(self):
        self.history: List[Any] = []

    # ------------------------------------------------------------------
    # Legacy choose() — degenerate single-option decision
    # ------------------------------------------------------------------

    def choose(
        self,
        options: list[Any],
        scores: list[float] | None = None,
    ) -> Any:
        if not options:
            return None

        if scores is None:
            decision = options[0]
        else:
            if len(options) != len(scores):
                raise ValueError(
                    "Options and scores must have the same length."
                )
            index = scores.index(max(scores))
            decision = options[index]

        self.history.append(decision)
        return decision

    # ------------------------------------------------------------------
    # Phase 5: plan/strategy comparison (reuses deterministic scoring)
    # ------------------------------------------------------------------

    def compare_plans(
        self,
        candidates: Optional[Sequence[Dict[str, Any]]],
        *,
        experience_stats: Optional[Dict[str, float]] = None,
        time_budget_s: Optional[float] = None,
        available_abilities: Optional[Sequence[str]] = None,
        available_capabilities: Optional[Sequence[str]] = None,
        environment: str = "default",
        user_constraints: Optional[Dict[str, Any]] = None,
        weights: Optional[Dict[str, float]] = None,
        world_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Score validated plan candidates deterministically (Phase 5).

        Accepts two shapes transparently:
        - NEW Phase-5 shape: CandidateStrategy dicts (as_dict layout)
        - LEGACY shape: {"mode": str, "plan": [...], "validation": {...}}

        Every candidate passes validation before scoring; invalid
        candidates are rejected with reasons and never executed.
        Returns {"choice": ..., "scores": [...], "reasons": [...], "record": DecisionRecord}.
        """
        import time as _time

        t0 = _time.perf_counter()
        exp_stats = dict(experience_stats or {})
        caps: List[str] = []
        for c in (available_capabilities or []):
            try:
                caps.append(Capability(str(c).upper()).value)
            except ValueError:
                caps.append(str(c).upper())
        abs_ = [str(a) for a in (available_abilities or [])]

        scored: List[Dict[str, Any]] = []
        valid_strategies: List[CandidateStrategy] = []
        rejected_reasons: List[Dict[str, Any]] = []

        for candidate in (candidates or []):
            data = dict(candidate or {})
            # Detect Phase-5 shape: has strategy_id / goal / steps
            if any(k in data for k in ("strategy_id", "goal", "steps")):
                cs = CandidateStrategy.from_dict(data)
                vresult = validate_candidate(
                    data,
                    known_capabilities=caps or None,
                    known_abilities=abs_ or None,
                    environment=environment,
                )
                if not vresult["ok"]:
                    rejected_reasons.append({
                        "strategy_id": cs.strategy_id,
                        "reason": "; ".join(p["detail"] for p in vresult["problems"]),
                        "problems": vresult["problems"],
                    })
                    continue
                valid_strategies.append(cs)
                continue

            # Legacy shape: {"mode": ..., "plan": [...], "validation": {...}}
            plan = list(data.get("plan", []) or [])
            validation = dict(data.get("validation", {}) or {})
            mode = str(data.get("mode", "legacy"))
            if not plan or not validation.get("valid", False):
                scored.append({
                    "candidate": candidate,
                    "score": float("-inf"),
                    "reason": f"{mode}: rejected — invalid or empty plan",
                })
                continue

            # Score the legacy plan using the same deterministic formula.
            step_caps = {str(c).upper()
                         for step in plan
                         for c in (step.get("required_capabilities", []) or [])}
            success_hits = sum(
                1 for c in step_caps
                if float(exp_stats.get(c, 0.0)) >= 0.5
            )
            success_prob = success_hits / max(1, len(step_caps))
            high_risk = sum(
                1 for step in plan
                if str(step.get("risk", "LOW")).upper() == "HIGH"
            )
            unverified = sum(
                1 for step in plan
                if not step.get("verification_criteria")
            )
            cost = len(plan)
            w = dict(weights or {})
            success_w = float(w.get("expected_success", 3.0))
            risk_w = float(w.get("risk", -1.5))
            cost_w = float(w.get("cost", -0.3))
            verif_w = float(w.get("verification_difficulty_penalty", -1.0))
            score = (
                success_w * success_prob
                + risk_w * high_risk
                + cost_w * cost
                + verif_w * unverified
            )
            if time_budget_s is not None:
                try:
                    estimate_s = cost * 30.0
                    if estimate_s > float(time_budget_s):
                        score -= 2.0
                except (TypeError, ValueError):
                    pass
            scored.append({
                "candidate": candidate,
                "score": round(score, 3),
                "reason": (
                    f"{mode}: success_prob={success_prob:.2f} steps={cost} "
                    f"high_risk={high_risk} unverified={unverified}"
                ),
            })

        # Phase-5 candidates: build DecisionRecord + pick winner.
        phase5: Optional[Dict[str, Any]] = None
        if valid_strategies:
            rec = decide_strategies(
                goal=str(valid_strategies[0].goal or ""),
                candidates=valid_strategies,
                experience_stats=exp_stats,
                available_abilities=abs_,
                available_capabilities=caps,
                environment=environment,
                user_constraints=user_constraints,
                weights=weights,
                decision_time_ms=1000.0 * (_time.perf_counter() - t0),
                world_state=world_state,
                time_budget_s=time_budget_s,
            )
            # legacy reasons list (per-candidate, human-readable)
            reasons: List[str] = []
            for cs in rec.candidates:
                s = rec.scores.get(cs.strategy_id, float("-inf"))
                r = rec.rejected_candidates
                is_rejected = any(
                    x.get("strategy_id") == cs.strategy_id for x in r
                )
                tag = "rejected" if is_rejected else f"score={s:.2f}"
                reasons.append(f"{cs.strategy_id}: {tag}")
            reasons.append(rec.selection_reason)
            phase5 = {
                "choice": rec.selected,
                "scores": rec.scores,
                "reasons": reasons,
                "record": rec,
            }

        # Merge: if both legacy and phase-5 candidates exist, phase-5 wins
        # (it is the authoritative path). Otherwise preserve legacy behavior.
        if phase5 is not None:
            # append any legacy-scored candidates as rejected for observability
            for sc in scored:
                if sc["score"] > float("-inf"):
                    phase5["reasons"].append(
                        f"legacy {sc['reason']}"
                    )
            return phase5

        # Pure legacy path (no Phase-5 candidates).
        valid = [x for x in scored if x["score"] > float("-inf")]
        if not valid:
            return {
                "choice": None,
                "scores": scored,
                "reasons": ["no valid candidate"],
            }
        valid.sort(key=lambda x: x["score"], reverse=True)
        choice = valid[0]["candidate"]
        self.history.append(choice)
        return {
            "choice": choice,
            "scores": scored,
            "reasons": [x["reason"] for x in scored],
        }

    def last(self) -> Any:
        if not self.history:
            return None
        return self.history[-1]

    def clear(self) -> None:
        self.history.clear()
