"""Phase 5: Decision Intelligence — deterministic strategy selection.

Hermetic tests over cognition.decision (schema, validation, scoring,
dominance, budget, constraints) plus the Brain/loop integration points.
No live model needed.
"""

import json

import pytest

from cognition.capabilities.capability import Capability
from cognition.decision import (
    CandidateStrategy,
    DecisionEngine,
    DEFAULT_WEIGHTS,
    decide_strategies,
    find_dominated,
    score_strategy,
    validate_candidate,
)


CAPS = [c.value for c in Capability]


def _steps(*args):
    """Flexible spec form. Accepts:
    _steps(READ, WRITE)          # spec tuples
    _steps(*READ)                # spread: 'goal', ['CAP']
    _steps('goal', ['CAP'])      # explicit pair
    """
    specs = []
    i = 0
    while i < len(args):
        a = args[i]
        if isinstance(a, tuple) and len(a) == 2 and isinstance(a[1], (list, tuple)):
            specs.append(a)
            i += 1
        elif isinstance(a, str) and i + 1 < len(args) and isinstance(args[i + 1], (list, tuple)):
            specs.append((a, list(args[i + 1])))
            i += 2
        else:
            raise ValueError(f"bad step spec near {a!r}")
    out = []
    for i, (goal, caps) in enumerate(specs, 1):
        out.append({"step_id": f"step-{i}", "goal": goal,
                    "required_capabilities": list(caps),
                    "verification_criteria": ["content non-empty"],
                    "risk": "LOW"})
    return out


READ = ("read the file", ["FILE_READ"])
WRITE = ("write the content", ["FILE_WRITE"])

# Spec shorthands: pass specs as positional tuples, e.g. _steps(READ, WRITE).
_READ = READ
_WRITE = WRITE


# ---------- Phase 2: candidate schema + validation gate ----------

def test_candidate_schema_fields():
    c = CandidateStrategy(strategy_id="s-1", goal="g", steps=[{"goal": "x"}])
    d = c.as_dict()
    for field in ("strategy_id", "goal", "steps", "required_capabilities",
                  "required_abilities", "dependencies", "estimated_cost",
                  "risk", "verification_difficulty", "expected_success",
                  "experience_support"):
        assert field in d


def test_invalid_candidates_discarded_before_scoring():
    bad = CandidateStrategy(strategy_id="bad", goal="g", steps=[])
    ok = CandidateStrategy(strategy_id="ok", goal="g",
                           steps=[{"step_id": "s1", "goal": "read",
                                   "required_capabilities": ["FILE_READ"]}],
                           required_capabilities=["FILE_READ"])
    rec = decide_strategies("g", [bad, ok])
    assert [c.strategy_id for c in rec.valid_candidates] == ["ok"]
    assert rec.rejected_candidates and rec.rejected_candidates[0]["strategy_id"] == "bad"
    assert "bad" not in rec.scores


def test_validate_candidate_rejects_unknown_capability_and_risk():
    r1 = validate_candidate({"goal": "g", "risk": "LOW", "steps": [
        {"step_id": "s1", "goal": "x", "required_capabilities": ["MIND_CONTROL"]}]})
    assert not r1["ok"] and any(p["code"] == "UNKNOWN_CAPABILITY" for p in r1["problems"])
    r2 = validate_candidate({"goal": "g", "risk": "EXTREME", "steps": [
        {"step_id": "s1", "goal": "x", "required_capabilities": ["FILE_READ"]}]})
    assert not r2["ok"] and any(p["code"] == "UNKNOWN_RISK" for p in r2["problems"])
    r3 = validate_candidate({"goal": "g", "risk": "LOW", "steps": [
        {"step_id": "s1", "goal": "x", "required_capabilities": ["FILE_READ"]}]})
    assert r3["ok"]


# ---------- Phase 3/4: deterministic scoring, weights configurable ----------

def test_scoring_is_deterministic_and_documented():
    from cognition.decision import BUDGET_PENALTY_WEIGHT
    c = CandidateStrategy(strategy_id="s", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"])
    a = score_strategy(c, available_capabilities=CAPS)
    b = score_strategy(c, available_capabilities=CAPS)
    assert a["score"] == b["score"]
    expected = set(DEFAULT_WEIGHTS) | {"budget_penalty"}
    assert set(a["components"]) == expected
    assert a["components"]["budget_penalty"] == 0.0  # not flagged over-budget
    assert BUDGET_PENALTY_WEIGHT < 0
    assert "success" in a["reason"] and "risk" in a["reason"]


def test_weighted_scoring_configurable():
    c = CandidateStrategy(strategy_id="s", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"], risk="HIGH")
    base = score_strategy(c, available_capabilities=CAPS)["score"]
    risk_neutral = score_strategy(c, available_capabilities=CAPS,
                                  weights={"risk": 0.0})["score"]
    assert risk_neutral > base  # removing the risk penalty raises the score


def test_capability_fit_rewards_available_capabilities():
    c = CandidateStrategy(strategy_id="s", goal="g", steps=_steps(READ, WRITE),
                          required_capabilities=["FILE_READ", "FILE_WRITE"])
    full = score_strategy(c, available_capabilities=CAPS)["components"]["capability_fit"]
    none = score_strategy(c, available_capabilities=[])["components"]["capability_fit"]
    assert full > none


# ---------- Phase 5: dominance ----------

def test_dominated_candidate_not_selected_with_reason():
    slow = CandidateStrategy(strategy_id="slow", goal="g", steps=_steps(*READ),
                             required_capabilities=["FILE_READ"], risk="LOW",
                             verification_difficulty="STRONG",
                             estimated_cost=5, estimated_latency_s=300)
    fast = CandidateStrategy(strategy_id="fast", goal="g", steps=_steps(*READ),
                             required_capabilities=["FILE_READ"], risk="LOW",
                             verification_difficulty="STRONG",
                             estimated_cost=1, estimated_latency_s=30)
    dom = find_dominated([slow, fast], scores={"slow": 1.0, "fast": 1.0})
    assert dom["slow"].dominated and dom["slow"].by == "fast"
    rec = decide_strategies("g", [slow, fast])
    assert rec.selected.strategy_id == "fast"


def test_not_dominated_when_safer():
    # The safer candidate is never dominated by a riskier one even if the
    # riskier one scores higher.
    risky = CandidateStrategy(strategy_id="risky", goal="g", steps=_steps(*WRITE),
                              required_capabilities=["FILE_WRITE"], risk="HIGH")
    safe = CandidateStrategy(strategy_id="safe", goal="g", steps=_steps(*WRITE),
                             required_capabilities=["FILE_WRITE"], risk="LOW",
                             verification_difficulty="STRONG")
    dom = find_dominated([safe, risky], scores={"safe": 3.0, "risky": 9.0})
    assert not dom["safe"].dominated


# ---------- Phase 6: experience preference (advisory) ----------

def test_experience_boost_prefers_previously_verified_strategy():
    exp = {"FILE_READ": 1.0}
    a = CandidateStrategy(strategy_id="a", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"],
                          experience_support=0.0)
    b = CandidateStrategy(strategy_id="b", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"],
                          experience_support=0.9)
    rec = decide_strategies("g", [a, b], experience_stats=exp)
    assert rec.selected.strategy_id == "b"
    assert rec.scores["b"] > rec.scores["a"]


# ---------- Phase 7: world-model preference ----------

def test_world_model_prefers_reuse_over_launch():
    ws = {"applications": ["notepad"], "by_type": {"file": 2}}
    reuse = CandidateStrategy(strategy_id="reuse", goal="g",
                              steps=_steps(("use the existing notepad window",
                                            ["APPLICATION_CONTROL"])),
                              required_capabilities=["APPLICATION_CONTROL"],
                              risk="MEDIUM")
    launch = CandidateStrategy(strategy_id="launch", goal="g",
                               steps=_steps(("open new notepad",
                                             ["APPLICATION_CONTROL"])),
                               required_capabilities=["APPLICATION_CONTROL"],
                               risk="MEDIUM")
    rec = decide_strategies("g", [launch, reuse], world_state=ws)
    assert rec.selected.strategy_id == "reuse"
    assert rec.scores["reuse"] > rec.scores["launch"]


def test_world_model_stale_state_never_blocks_selection():
    # A garbage world state must not break or bias the decision.
    c = CandidateStrategy(strategy_id="s", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"])
    base = score_strategy(c, available_capabilities=CAPS)["score"]
    weird = score_strategy(c, available_capabilities=CAPS,
                           world_state={"applications": "not-a-list",
                                        "by_type": {"file": "many"}})["score"]
    assert base == weird


# ---------- Phase 8: risk-aware selection ----------

def test_higher_risk_needs_meaningful_advantage():
    risky = CandidateStrategy(strategy_id="risky", goal="g",
                              steps=_steps(("run system change", ["TERMINAL_EXECUTE"])),
                              required_capabilities=["TERMINAL_EXECUTE"],
                              risk="HIGH", expected_success=0.95,
                              estimated_latency_s=10)
    safe = CandidateStrategy(strategy_id="safe", goal="g",
                             steps=_steps(*READ),
                             required_capabilities=["FILE_READ"],
                             risk="LOW", verification_difficulty="STRONG")
    rec = decide_strategies("g", [risky, safe])
    assert rec.selected.strategy_id == "safe"


# ---------- Phase 9: verification-aware selection ----------

def test_unverified_strategy_loses_to_verified():
    unverified = CandidateStrategy(strategy_id="uv", goal="g",
                                   steps=[{"step_id": "s1", "goal": "write",
                                           "required_capabilities": ["FILE_WRITE"]}],
                                   required_capabilities=["FILE_WRITE"],
                                   verification_difficulty="MINIMAL")
    verified = CandidateStrategy(strategy_id="v", goal="g",
                                 steps=[{"step_id": "s1", "goal": "write",
                                         "required_capabilities": ["FILE_WRITE"],
                                         "verification_criteria": ["content non-empty"]}],
                                 required_capabilities=["FILE_WRITE"],
                                 verification_difficulty="STRONG")
    rec = decide_strategies("g", [unverified, verified])
    assert rec.selected.strategy_id == "v"


# ---------- Phase 10: explicit user constraints ----------

def test_user_constraint_overrides_score():
    risky_fast = CandidateStrategy(strategy_id="risky", goal="g",
                                   steps=_steps(*WRITE),
                                   required_capabilities=["FILE_WRITE"],
                                   risk="HIGH", expected_success=1.0)
    safe_slow = CandidateStrategy(strategy_id="safe", goal="g",
                                  steps=_steps(*WRITE),
                                  required_capabilities=["FILE_WRITE"],
                                  risk="LOW")
    rec = decide_strategies("g", [risky_fast, safe_slow],
                            user_constraints={"require_risk": "LOW"})
    assert rec.user_constraint_applied
    assert rec.selected.strategy_id == "safe"


def test_unsatisfiable_constraint_falls_back_honestly():
    only = CandidateStrategy(strategy_id="only", goal="g",
                             steps=_steps(*READ),
                             required_capabilities=["FILE_READ"], risk="MEDIUM")
    rec = decide_strategies("g", [only],
                            user_constraints={"require_risk": "LOW"})
    # Constraint cannot be met; the only valid candidate still runs but the
    # applied flag stays honest.
    assert not rec.user_constraint_applied
    assert rec.selected.strategy_id == "only"


# ---------- Phase 11: tie-breaking (documented order) ----------

def test_tie_break_prefers_safer_then_verifiable():
    # Equal-score candidates (risk zeroed via weights): risk tie-break picks b.
    a = CandidateStrategy(strategy_id="a", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"], risk="MEDIUM",
                          verification_difficulty="STANDARD")
    b = CandidateStrategy(strategy_id="b", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"], risk="LOW",
                          verification_difficulty="STANDARD")
    neutral = {"risk": 0.0}
    assert score_strategy(a, available_capabilities=CAPS, weights=neutral)["score"] == \
           score_strategy(b, available_capabilities=CAPS, weights=neutral)["score"]
    rec = decide_strategies("g", [a, b], weights=neutral)
    assert rec.selected.strategy_id == "b"  # safer wins the tie
    # Same risk, different verification: more verifiable wins via tie-break.
    c = CandidateStrategy(strategy_id="c", goal="g", steps=_steps(*READ),
                          required_capabilities=["FILE_READ"], risk="LOW",
                          verification_difficulty="STRONG")
    rec2 = decide_strategies("g", [b, c])
    assert rec2.selected.strategy_id == "c"


# ---------- Phase 12: LLM proposes, deterministic layer decides ----------

def test_engine_ignores_model_scores_and_uses_own_ranking():
    engine = DecisionEngine()
    good = CandidateStrategy(strategy_id="good", goal="g", steps=_steps(*READ),
                             required_capabilities=["FILE_READ"], risk="LOW",
                             verification_difficulty="STRONG")
    bad = CandidateStrategy(strategy_id="bad", goal="g",
                            steps=_steps(("run system change", ["TERMINAL_EXECUTE"])),
                            required_capabilities=["TERMINAL_EXECUTE"],
                            risk="HIGH", expected_success=1.0)
    # Phase-5 dicts through compare_plans: the engine re-scores internally.
    result = engine.compare_plans([good.as_dict(), bad.as_dict()],
                                  available_capabilities=CAPS)
    assert result["choice"].strategy_id == "good"
    assert isinstance(result["record"].scores, dict)


def test_model_assisted_proposal_never_bypasses_validation():
    engine = DecisionEngine()
    malformed = {"strategy_id": "m", "goal": "", "steps": []}
    result = engine.compare_plans([malformed])
    assert result["choice"] is None


# ---------- Phase 13: replanning integration ----------

def test_replan_recovery_uses_decision_ranking():
    import asyncio
    from abilities.ability_manager import AbilityManager
    from abilities.base_ability import BaseAbility
    from abilities.tool_matcher import ToolMatcher
    from cognition.capabilities.registry import CapabilityRegistry
    from cognition.planner.planner import Planner
    from cognition.task_manager.task_manager import TaskManager
    from orchestrator.autonomous import AutonomousLoop
    from security.permissions.policy_manager import PolicyManager
    from system.observability.trace import Tracer

    class AlwaysFail(BaseAbility):
        def __init__(self):
            super().__init__("always-fail", "fails")
            self.calls = 0

        def execute(self, *args, **kwargs):
            self.calls += 1
            raise RuntimeError("tool plane down")

    policy = PolicyManager()
    abilities = AbilityManager(policy)
    fail = AlwaysFail()
    abilities.register(fail)
    registry = CapabilityRegistry()
    registry.register_provider("MATH", "tool", "always-fail",
                               ability_manager=abilities)
    matcher = ToolMatcher(abilities, policy, None, registry)
    loop = AutonomousLoop(Planner(), matcher, TaskManager(), Tracer())
    loop.max_replans = 1
    report = loop.run("recover", ["Calculate 1+1"], correlation_id="di-recover")
    assert report["status"] == "failed"
    assert report["replans"] == 1
    assert fail.calls >= 2  # recovery wording re-executed through validation


# ---------- Phase 14/18: budget enforcement + policy isolation ----------

def test_budget_enforcement_penalizes_over_budget_strategy():
    fast = CandidateStrategy(strategy_id="fast", goal="g", steps=_steps(*READ),
                             required_capabilities=["FILE_READ"],
                             estimated_latency_s=30)
    slow = CandidateStrategy(strategy_id="slow", goal="g", steps=_steps(*READ),
                             required_capabilities=["FILE_READ"],
                             verification_difficulty="STRONG",
                             estimated_latency_s=500)
    rec = decide_strategies("g", [slow, fast], time_budget_s=120)
    assert "slow" in rec.over_budget_ids
    assert rec.selected.strategy_id == "fast"


def test_policy_denial_removes_candidate_from_selection():
    """Policy isolation: a permission-denied candidate is not selectable."""
    engine = DecisionEngine()
    denied = {"mode": "cognitive",
              "plan": [{"step_id": "s1", "required_capabilities": ["FILE_READ"],
                        "verification_criteria": ["x"], "risk": "LOW"}],
              "validation": {"valid": False,
                             "problems": [{"code": "PERMISSION_DENIED",
                                           "detail": "FILE_READ denied"}]}}
    result = engine.compare_plans([denied])
    assert result["choice"] is None  # never selected, never executed


def test_decision_engine_never_executes_tools():
    """The decision layer only ranks; it has no execution surface."""
    engine = DecisionEngine()
    for attr in ("execute", "run", "run_cycle", "execute_tool"):
        assert not hasattr(engine, attr)
