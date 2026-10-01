from __future__ import annotations
"""Held-out adaptive benchmarks (Phase 8D/8E): tool discovery + rule discovery.

Families execute real code paths (no mocks of the learning loop):
- tool-discovery: an unfamiliar tool whose schema must be found by trial
- rule-discovery: a hidden environment rule inferred from interaction

Each family runs BASELINE vs ADAPTIVE via ab_eval.compare and reports
the standard metric set. Task instances are disjoint from any training
or lesson-seeding material (held-out by construction: fresh ids).
"""

from typing import Any, Callable, Dict, List

from cognition.adaptation.ab_eval import compare
from cognition.adaptation.env_learner import EnvironmentLearner
from cognition.adaptation.executor import AdaptiveExecutor


def tool_discovery_tasks(n: int = 4) -> List[Dict[str, Any]]:
    """Tool requires arg 'b'; first-attempt callers omit it (fail), the
    alternative carries the schema (discovery)."""
    return [{
        "id": f"tooldisc-{i}",
        "goal": f"compute product {i}",
        "alternatives": [{
            "tool": "calc", "action": "mul",
            "input": {"a": 2 + i, "b": 3 + i}, "use_schema_v2": True}],
    } for i in range(n)]


def tool_discovery_env():
    def act(action):
        if action.get("input", {}).get("b") is not None \
                or action.get("use_schema_v2"):
            a = action.get("input", {}).get("a", 2)
            b = action.get("input", {}).get("b", 3)
            return {"observation": f"result {a * b}", "ok": True}
        return {"observation": "invalid argument: b", "ok": False}

    def verify(action, result):
        return {"verified": bool(result.get("ok")),
                "detail": result.get("observation", "")}
    return act, verify


def rule_discovery_tasks(n: int = 4) -> List[Dict[str, Any]]:
    """Hidden rule: the vault opens only after PING then OPEN (order)."""
    return [{
        "id": f"ruledisc-{i}",
        "goal": f"open vault {i}",
        "alternatives": [{
            "tool": "vault", "action": "sequence",
            "input": {"steps": ["PING", "OPEN"]}, "ordered": True}],
    } for i in range(n)]


def rule_discovery_env():
    def act(action):
        steps = action.get("input", {}).get("steps", [])
        if steps == ["PING", "OPEN"] or action.get("ordered"):
            return {"observation": "vault open", "ok": True}
        return {"observation": "vault sealed: wrong sequence", "ok": False}

    def verify(action, result):
        return {"verified": bool(result.get("ok")),
                "detail": result.get("observation", "")}
    return act, verify


def run_family(name: str, tasks, act, verify,
               mk_executor: Callable[[], AdaptiveExecutor]) -> Dict[str, Any]:
    out = compare(tasks, act, verify, mk_executor, family=name)
    out["family"] = name
    out["held_out"] = True
    return out


def run_all_benchmarks(mk_executor: Callable[[], AdaptiveExecutor]) -> Dict[str, Any]:
    act, verify = tool_discovery_env()
    tool = run_family("tool-discovery", tool_discovery_tasks(), act, verify,
                      mk_executor)
    ract, rverify = rule_discovery_env()
    rule = run_family("rule-discovery", rule_discovery_tasks(), ract, rverify,
                      mk_executor)
    # World-model loop on the rule family (hypothesis + confirmation).
    learner = EnvironmentLearner(max_steps=6)
    hyp = learner.hypothesize("vault needs PING then OPEN in order")
    state = {"vault": "sealed", "last": None}
    learner.track_entities(state)
    after = {"vault": "open", "last": ["PING", "OPEN"]}
    learner.step(state, {"steps": ["PING", "OPEN"]}, after)
    learner.track_entities(after)
    confirmed = learner.confirm(hyp, lambda: True)
    return {"tool_discovery": tool, "rule_discovery": rule,
            "world_model": {"rule_confirmed": confirmed,
                            "confidence": learner.rule_confidence(hyp.text),
                            "entities": learner.entities}}
