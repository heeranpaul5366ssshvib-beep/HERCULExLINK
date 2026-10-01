"""Phase L-B: effect classification, resume policy, compensation, adversarial."""

import pytest

from abilities.base_ability import BaseAbility
from abilities.tool_matcher import ToolMatcher
from cognition.capabilities.capability import Capability
from cognition.capabilities.effects import (
    EffectClass,
    claim_allowed,
    coerce_effect,
    default_effect_for,
    describe_semantics,
)
from cognition.planner.capable import build_capable_step
from orchestrator.resume import ResumePlanner
from runtime.initializer import RuntimeInitializer
from security.permissions.policy_manager import PolicyManager
from abilities.ability_manager import AbilityManager
from cognition.capabilities.registry import CapabilityRegistry
from system.observability.trace import (
    explain_compensation_required,
    explain_resume_blocked,
    explain_step_replayed,
    explain_step_skipped,
)


class EchoAbility(BaseAbility):
    def __init__(self, name="echo", result="content-present"):
        super().__init__(name, f"test {name}")
        self.calls = 0
        self.result = result

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": self.result}


@pytest.fixture()
def rig():
    abilities = AbilityManager(PolicyManager())
    abilities.register(EchoAbility("reader"))
    abilities.register(EchoAbility("writer", result="written-ok"))
    abilities.register(EchoAbility("comp", result="compensation done"))
    abilities.register(EchoAbility("term"))
    registry = CapabilityRegistry()
    registry.register_provider("FILE_READ", "tool", "reader", ability_manager=abilities)
    registry.register_provider("FILE_WRITE", "tool", "writer", ability_manager=abilities)
    registry.register_provider("FILE_WRITE", "tool", "comp", ability_manager=abilities)
    registry.register_provider("TERMINAL_EXECUTE", "tool", "term", ability_manager=abilities)
    matcher = ToolMatcher(abilities, abilities.policy, None, registry)
    planner = ResumePlanner(task_manager=None, matcher=matcher)
    return abilities, registry, matcher, planner


def _step(sid, caps, effect=None, **extra):
    base = {"step_id": sid, "description": f"step {sid}", "required_capabilities": caps,
            "risk": "LOW", "verification_criteria": ["ok"], "dependencies": []}
    if effect:
        base["effect"] = effect
    base.update(extra)
    return base


def test_effect_defaults_and_claim_rule():
    assert default_effect_for([Capability.FILE_READ]) == EffectClass.READ_ONLY
    assert default_effect_for([Capability.MATH]) == EffectClass.IDEMPOTENT
    assert default_effect_for([Capability.FILE_WRITE]) == EffectClass.EFFECTFUL
    assert default_effect_for([Capability.DATABASE_WRITE]) == EffectClass.COMPENSATABLE
    assert default_effect_for([Capability.TERMINAL_EXECUTE]) == EffectClass.NON_RESUMABLE
    assert default_effect_for([Capability.FILE_READ, Capability.FILE_WRITE]) == EffectClass.EFFECTFUL
    assert claim_allowed(EffectClass.NON_RESUMABLE, EffectClass.EFFECTFUL) is True  # stricter ok
    assert claim_allowed(EffectClass.IDEMPOTENT, EffectClass.EFFECTFUL) is False  # looser rejected
    with pytest.raises(ValueError, match="unknown effect"):
        coerce_effect("SOMETIMES")
    for effect in EffectClass:
        assert "exactly-once" not in describe_semantics(effect)  # never claimed


def test_step_metadata_carries_effect_contract():
    step = build_capable_step("step-1", "Read this file")
    assert step["effect"] == "READ_ONLY"
    assert step["state_check"] == {} and step["compensation"] is None
    assert step["resume_policy"] == "default"
    writing = build_capable_step("step-2", "Write the file",
                                 compensation={"capability": "FILE_WRITE", "description": "revert"})
    assert writing["effect"] == "EFFECTFUL"
    assert writing["compensation"]["capability"] == "FILE_WRITE"


def test_read_only_skip_and_unknown_replay(rig):
    _, _, matcher, planner = rig
    verified = {"status": "completed", "verification": {"passed": True}}
    d = planner._decide(None, _step("s1", ["FILE_READ"], "READ_ONLY"), "s1", verified)
    assert (d.action, d.step_id) == ("SKIP", "s1")
    d2 = planner._decide(None, _step("s2", ["FILE_READ"], "READ_ONLY"), "s2",
                         {"status": "running"})
    assert d2.action == "REPLAY"  # unknown read state: safe re-read
    assert matcher is not None


def test_idempotent_check_gates_skip(rig):
    abilities, _, matcher, planner = rig
    check = {"capability": "FILE_READ", "input": "anything", "expect": "content-present"}
    verified = {"status": "completed", "verification": {"passed": True}}
    step = _step("s", ["MATH"], "IDEMPOTENT", state_check=check)
    d = planner._decide(None, step, "s", verified)
    assert d.action == "REPLAY" and d.detail.get("state_check") is True
    ran = planner.run_state_check({**step, "state_check": {**check, "capability": "FILE_READ"}})
    assert ran == {"ran": True, "passed": True, "detail": "state present"}
    missing = planner.run_state_check({**step, "state_check": {**check, "expect": "absent-xyz"}})
    assert missing["passed"] is False
    assert abilities.get("reader").calls == 2  # checks execute read-only tools
    no_check_unknown = planner._decide(None, _step("s", ["MATH"], "IDEMPOTENT"), "s",
                                       {"status": "running"})
    assert no_check_unknown.action == "BLOCK"  # unknown + no check: refuse


def test_effectful_verified_complete_blocked_by_default(rig):
    _, _, _, planner = rig
    verified = {"status": "completed", "verification": {"passed": True}}
    d = planner._decide(None, _step("s", ["FILE_WRITE"], "EFFECTFUL"), "s", verified)
    assert d.action == "BLOCK"
    allowed = planner._decide(None, _step("s", ["FILE_WRITE"], "EFFECTFUL", resume_policy="replay-ok"),
                              "s", verified)
    assert allowed.action == "REPLAY"


def test_false_idempotency_rejected(rig):
    _, _, _, planner = rig
    verified = {"status": "completed", "verification": {"passed": True}}
    d = planner._decide(None, _step("s", ["FILE_WRITE"], "IDEMPOTENT"), "s", verified)
    assert d.action == "BLOCK"
    assert "false idempotency" in d.reason


def test_compensatable_flow_and_missing_compensation(rig):
    _, _, matcher, planner = rig
    verified = {"status": "completed", "verification": {"passed": True}}
    comp = {"capability": "FILE_WRITE", "description": "revert the write"}
    d = planner._decide(None, _step("s", ["FILE_WRITE"], "COMPENSATABLE", compensation=comp),
                        "s", verified)
    assert d.action == "COMPENSATE"
    out = planner.execute_compensation(_step("s", ["FILE_WRITE"], "COMPENSATABLE", compensation=comp))
    assert out["status"] == "compensated"
    no_comp = planner._decide(None, _step("s", ["FILE_WRITE"], "COMPENSATABLE"), "s", verified)
    assert no_comp.action == "BLOCK"
    bad = planner.execute_compensation(_step("s", ["FILE_WRITE"], "COMPENSATABLE",
                                             compensation={"capability": "NOPE_CAP"}))
    assert bad["status"] == "blocked"
    assert matcher is not None


def test_non_resumable_needs_restart(rig):
    _, _, _, planner = rig
    d = planner._decide(None, _step("s", ["TERMINAL_EXECUTE"], "NON_RESUMABLE"), "s",
                        {"status": "completed", "verification": {"passed": True}})
    assert d.action == "BLOCK"
    fresh = planner._decide(None, _step("s", ["TERMINAL_EXECUTE"], "NON_RESUMABLE"), "s", None)
    assert fresh.action == "REPLAY"  # never attempted: normal validated run


def test_malformed_and_stale_checkpoints(rig):
    _, _, _, planner = rig
    assert planner._stored_states("missing") == {}
    planner.tasks = {"not": "a manager"}  # malformed manager: guarded
    assert planner._stored_states("x") == {}
    d = planner._decide(None, {"step_id": "s", "required_capabilities": ["FILE_READ"],
                               "effect": "SOMETIMES", "risk": "LOW", "verification_criteria": ["ok"],
                               "dependencies": []}, "s", None)
    assert d.action == "BLOCK"


def test_changed_permissions_and_tools_block(rig):
    abilities, _, matcher, planner = rig
    verified = {"status": "completed", "verification": {"passed": True}}
    step = _step("s", ["FILE_WRITE"], "EFFECTFUL", resume_policy="replay-ok")
    assert planner._decide(None, step, "s", verified).action == "REPLAY"
    abilities.policy.set_permission("FILE_WRITE", False)
    try:
        assert planner._decide(None, step, "s", verified).action == "BLOCK"
    finally:
        abilities.policy.set_permission("FILE_WRITE", True)
    abilities.disable("writer")
    abilities.disable("comp")
    try:
        assert planner._decide(None, step, "s", verified).action == "BLOCK"
    finally:
        abilities.enable("writer")
        abilities.enable("comp")
    assert matcher is not None


def test_why_explainers_derive_from_metadata():
    skipped = {"step_id": "s1", "action": "SKIP", "reason": "read-only verified", "detail": {}}
    assert "s1" in explain_step_skipped(skipped)["answer"]
    replayed = {"step_id": "s2", "action": "REPLAY", "reason": "not complete", "detail": {}}
    assert "s2" in explain_step_replayed(replayed)["answer"]
    comp = {"step_id": "s3", "action": "COMPENSATE", "reason": "undo first", "detail": {}}
    assert "s3" in explain_compensation_required(comp, {"status": "compensated"})["answer"]
    blocked = {"step_id": "s4", "action": "BLOCK", "reason": "unsafe", "detail": {}}
    assert "s4" in explain_resume_blocked(blocked)["answer"]


def test_brain_resume_skips_verified_replays_rest():
    init = RuntimeInitializer()
    services = init.initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.register(EchoAbility("echo-file"))
    brain.register_capability("FILE_READ", "tool", "echo-file")
    tasks = orch.task_manager
    tid = tasks.create_task("Handle files")
    tasks.queue_task(tid)
    tasks.start(tid)
    task = tasks.get(tid)
    task.setdefault("metadata", {})["capability_states"] = {
        "step-1": {"status": "completed", "required_capabilities": ["FILE_READ"],
                   "verification": {"passed": True}, "effect": "READ_ONLY"},
    }
    report = brain.run_cycle("Handle files", steps=["Read this file", "Read this file again"],
                             task_id=tid, correlation_id="resume-l")
    assert report["status"] == "completed"
    assert orch.abilities.get("echo-file").calls == 1  # step-1 skipped, step-2 ran
    stages = brain._tracer.get("resume-l").as_dict()["stages"]
    assert "resume_attempt" in stages


def test_brain_resume_blocked_leaves_task_safe():
    init = RuntimeInitializer()
    services = init.initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.register(EchoAbility("echo-w", result="written"))
    brain.register_capability("FILE_WRITE", "tool", "echo-w")
    tasks = orch.task_manager
    tid = tasks.create_task("Write files")
    tasks.queue_task(tid)
    tasks.start(tid)
    task = tasks.get(tid)
    task.setdefault("metadata", {})["capability_states"] = {
        "step-1": {"status": "completed", "required_capabilities": ["FILE_WRITE"],
                   "verification": {"passed": True}, "effect": "EFFECTFUL"},
    }
    report = brain.run_cycle("Write files", steps=["Write the file"], task_id=tid,
                             correlation_id="resume-blocked")
    assert report["status"] == "blocked"
    assert orch.abilities.get("echo-w").calls == 0  # nothing replayed
    assert tasks.status(tid) == "PAUSED"  # parked, not orphaned
    again = brain.run_cycle("Write files", steps=["Write the file"], task_id=tid)
    assert again["status"] == "blocked"  # duplicate resume: still safe


def test_duplicate_resume_after_completion_is_cached():
    init = RuntimeInitializer()
    services = init.initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.register(EchoAbility("echo-file"))
    brain.register_capability("FILE_READ", "tool", "echo-file")
    first = brain.run_cycle("Read this file")
    calls = orch.abilities.get("echo-file").calls
    second = brain.run_cycle("Read this file", task_id=first["task_id"])
    assert second.get("idempotent") is True
    assert orch.abilities.get("echo-file").calls == calls
