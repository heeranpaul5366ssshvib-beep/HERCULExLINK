from __future__ import annotations
"""Phase L1: planner ↔ SkillManager integration.

Only validated skills are consulted; every skill-built step still
passes capability validation, tool matching, policy, autonomy
gates, and verification. Deterministic unit scope (one live
end-to-end proof included).
"""

import pytest

from abilities.ability_manager import AbilityManager
from abilities.base_ability import BaseAbility
from cognition.capabilities.registry import CapabilityRegistry
from cognition.planner.planner import Planner
from cognition.planner.validation import validate_plan
from cognition.skills import Skill, SkillManager
from security.permissions.policy_manager import PolicyManager


class EchoAbility(BaseAbility):
    def __init__(self, name="echo", result="ok"):
        super().__init__(name, f"test {name}")
        self.result = result

    def execute(self, *args, **kwargs):
        return {"status": "success", "content": self.result}


def _manager():
    return SkillManager()


def _math_skill(**overrides):
    data = {"skill_id": "calc", "description": "calculate 9+9 quickly",
            "required_capabilities": ["MATH"], "procedure": ["Calculate 9+9"]}
    data.update(overrides)
    return Skill(**data)


def _stack():
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    abilities.register(EchoAbility("calc-stub", result="42"))
    registry = CapabilityRegistry()
    registry.register_provider("MATH", "tool", "calc-stub",
                               ability_manager=abilities)
    return abilities, policy, registry


# 1. planner resolves validated skill
def test_resolves_validated_skill():
    mgr = _manager()
    mgr.register(_math_skill(), validate=True)
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("calculate 9+9 quickly", allow_skills=True)
    assert len(plan) == 1
    assert plan[0]["skill_id"] == "calc"
    assert plan[0]["skill_version"] == "1.0.0"
    assert plan[0]["required_capabilities"] == ["MATH"]
    assert plan[0]["verification_criteria"]  # verification still attached


# 2. planner ignores invalid (unvalidated/proposed) skill
def test_ignores_unvalidated_skill():
    mgr = _manager()
    mgr.register(_math_skill())  # proposed, not validated
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("calculate 9+9 quickly", allow_skills=True)
    assert all("skill_id" not in s for s in plan)


# 3. unavailable skill (no provider) fails matching honestly
def test_unavailable_skill_rejected_by_matching():
    from abilities.tool_matcher import ToolMatchError, ToolMatcher

    mgr = _manager()
    mgr.register(_math_skill(skill_id="ghost",
                             required_capabilities=["VISION_ANALYSIS"],
                             procedure=["Analyze the nebula"]), validate=True)
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("analyze the nebula now", allow_skills=True)
    assert plan[0].get("skill_id") == "ghost"
    abilities, policy, registry = _stack()
    matcher = ToolMatcher(abilities, policy, None, registry)
    with pytest.raises(ToolMatchError) as info:
        matcher.match(plan[0])
    assert info.value.code in ("NO_HEALTHY_PROVIDER", "PARTIAL_COVERAGE",
                               "UNKNOWN_CAPABILITY")


# 4. policy still applies to skill-built steps
def test_policy_denies_skill_steps():
    mgr = _manager()
    mgr.register(_math_skill(), validate=True)
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("calculate 9+9 quickly", allow_skills=True)
    abilities, policy, registry = _stack()
    policy.set_permission("MATH", False)
    try:
        report = validate_plan(plan, capability_registry=registry,
                               policy_manager=policy,
                               ability_manager=abilities, goal="g")
    finally:
        policy.set_permission("MATH", True)
    assert report["valid"] is False
    assert any(p["code"] == "PERMISSION_CONFLICT" for p in report["problems"])


# 5. autonomy level still applies to skill goals
def test_autonomy_gate_applies():
    from autonomy.levels import evaluate_gate

    assert evaluate_gate(2, "calculate 9+9 quickly")["allowed"] is True
    assert evaluate_gate(0, "calculate 9+9 quickly")["allowed"] is False


# 6. verification still applies end-to-end
def test_skill_execution_verified(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    skills = services["skills"]
    skills._skills.clear()
    skills.set_store_path(tmp_path / "skills.json")
    skills.register(_math_skill(), validate=True)
    report = services["brain"].run_cycle("calculate 9+9 quickly")
    assert report["status"] == "completed"
    assert report["verification"]["passed_steps"] >= 1


# 7. missing skill produces a capability gap, not a silent plan
def test_missing_skill_is_gap():
    mgr = _manager()
    verdict = mgr.evaluate_gap("levitate the moon",
                               required_capabilities=["QUANTUM_LEVITATION"])
    assert verdict["resolution"] == "capability_gap"
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("levitate the moon")
    assert all("skill_id" not in s for s in plan)


# 8. skill execution failure is observable (validation verdict, not silence)
def test_skill_failure_observable():
    mgr = _manager()
    mgr.register(_math_skill(skill_id="bad",
                             required_capabilities=["NO_SUCH_CAP"],
                             procedure=["Do impossible math"]), validate=True)
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("do impossible math fast", allow_skills=True)
    _, policy, registry = _stack()
    report = validate_plan(plan, capability_registry=registry,
                           policy_manager=policy, goal="g")
    assert report["valid"] is False
    assert report["problems"], "failure must carry structured problems"


# 9. skills never self-install through planning
def test_no_self_install():
    mgr = _manager()
    before = len(mgr.all())
    planner = Planner().configure_skills(mgr)
    planner.create_capable_plan("calculate 9+9 quickly", allow_skills=True)
    planner.create_capable_plan("something entirely new here")
    assert len(mgr.all()) == before


def test_explicit_steps_beat_skills():
    mgr = _manager()
    mgr.register(_math_skill(), validate=True)
    planner = Planner().configure_skills(mgr)
    plan = planner.create_capable_plan("calculate 9+9 quickly",
                                       ["Read this file"])
    assert all("skill_id" not in s for s in plan)
    assert plan[0]["required_capabilities"] == ["FILE_READ"]


def test_no_manager_is_legacy_path():
    planner = Planner()
    plan = planner.create_capable_plan("calculate 9+9 quickly", allow_skills=True)
    assert all("skill_id" not in s for s in plan)
