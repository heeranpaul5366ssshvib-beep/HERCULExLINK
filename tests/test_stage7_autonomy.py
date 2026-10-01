"""Stage 7: multi-step autonomy, observation, bounded replan, resume,
experience-aware planning, consciousness lifecycle, goal lifecycle,
self-evaluation. Loop-level tests use stubs (fast, deterministic);
Brain-level tests run on the mock model (no live LLM needed)."""

import os

import pytest

from abilities.ability_manager import AbilityManager
from abilities.base_ability import BaseAbility
from abilities.tool_matcher import ToolMatcher
from brain.goal_manager import GoalManager
from cognition.capabilities.registry import CapabilityRegistry
from cognition.experience.experience_manager import ExperienceManager
from cognition.planner.capable import build_capable_plan, decompose_goal
from cognition.planner.planner import Planner
from cognition.self_evaluation.self_evaluator import SelfEvaluator
from cognition.task_manager.task_manager import TaskManager
from orchestrator.autonomous import AutonomousLoop
from security.permissions.policy_manager import PolicyManager
from system.observability.trace import Tracer


class EchoAbility(BaseAbility):
    def __init__(self, name="echo", result="ok-content"):
        super().__init__(name, f"test {name}")
        self.calls = 0
        self.result = result

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": self.result}


class AlwaysFailAbility(BaseAbility):
    def __init__(self, name="always-fail"):
        super().__init__(name, "always fails")
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("simulated persistent failure")


class FlapOnceAbility(BaseAbility):
    """Fails once, then succeeds: exercises genuine recovery via replan."""

    def __init__(self, name="flap-once"):
        super().__init__(name, "fails once then recovers")
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("simulated transient failure")
        return {"status": "success", "content": "recovered-content"}


class HighRiskAbility(BaseAbility):
    def __init__(self, name="danger-stub"):
        super().__init__(name, "high risk stub", risk="HIGH",
                         permissions=["TERMINAL_EXECUTE"])
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": "should never run unapproved"}


def make_world(extra_abilities=(), max_replans=2, max_step_retries=1,
               time_budget=None):
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    abilities.register(EchoAbility("files-stub"))
    abilities.register(EchoAbility("calc-stub", result="42"))
    for ability in extra_abilities:
        abilities.register(ability)
    registry = CapabilityRegistry()
    registry.register_provider("FILE_READ", "tool", "files-stub",
                               ability_manager=abilities)
    registry.register_provider("MATH", "tool", "calc-stub",
                               ability_manager=abilities)
    matcher = ToolMatcher(abilities, policy, None, registry)
    planner = Planner()
    tasks = TaskManager()
    tracer = Tracer()
    kwargs = {"max_replans": max_replans, "max_step_retries": max_step_retries}
    if time_budget is not None:
        kwargs["max_total_execution_time"] = time_budget
    loop = AutonomousLoop(planner, matcher, tasks, tracer, **kwargs)
    return abilities, policy, registry, matcher, planner, tasks, tracer, loop


# ---------- Phase 2: decomposition + contract ----------

def test_decompose_goal_splits_sequences():
    parts = decompose_goal("Create a file then read the file then calculate 2+2")
    assert parts == ["Create a file", "read the file", "calculate 2+2"]


def test_decompose_goal_single_action_unchanged():
    assert decompose_goal("calculate 25 * 4") == ["calculate 25 * 4"]
    assert decompose_goal("   ") != []


def test_plan_steps_carry_full_contract():
    plan = build_capable_plan("do things", ["Read this file"], chain=True)
    step = plan[0]
    for field in ("step_id", "goal", "dependencies", "required_capabilities",
                  "required_ability", "inputs", "expected_output",
                  "verification_criteria", "risk"):
        assert field in step, field
    assert step["required_capabilities"] == ["FILE_READ"]
    assert step["verification_criteria"]


def test_chained_plan_links_dependencies():
    plan = build_capable_plan("g", ["Read this file", "Calculate 1+1"], chain=True)
    assert plan[0]["dependencies"] == []
    assert plan[1]["dependencies"] == ["step-1"]


# ---------- Phase 2/3: multi-step + observation ----------

def test_multi_step_chained_execution_in_order():
    world = make_world()
    _, _, _, _, _, tasks, tracer, loop = world
    tid = tasks.create_task("multi")
    report = loop.run("multi", ["Read this file", "Read this file again"],
                      task_id=tid, correlation_id="s7-multi", chain=True)
    assert report["status"] == "completed"
    assert report["completed"] == ["step-1", "step-2"]
    stages = tracer.get("s7-multi").as_dict()["stages"]
    assert "observation" in stages
    assert "step" in stages
    assert [e["step_id"] for e in stages["step"]] == ["step-1", "step-2"]


def test_dependent_step_blocked_when_prerequisite_fails():
    abilities, _, _, _, _, _, _, loop = make_world(
        extra_abilities=[AlwaysFailAbility("fail-read")])
    loop.matcher.registry.register_provider("FILE_READ", "tool", "fail-read",
                                            ability_manager=abilities)
    # Sole FILE_READ provider fails at execution (passes validation), so
    # the dependent MATH step must block instead of running on assumption.
    abilities.get("files-stub").disable()
    loop.max_replans = 0  # no replan noise: straight fail -> blocked dependent
    tid = loop.tasks.create_task("blocked-demo")
    try:
        report = loop.run(
            "blocked-demo",
            [{"description": "Read this file", "required_capabilities": ["FILE_READ"]},
             {"description": "Calculate 1+1", "required_capabilities": ["MATH"],
              "dependencies": ["step-1"]}],
            task_id=tid, correlation_id="s7-blocked")
    finally:
        abilities.get("files-stub").enable()
    assert report["status"] == "failed"
    reasons = [f.get("reason", "") for f in report["failed"]]
    assert any("blocked" in r for r in reasons), reasons
    assert abilities.get("calc-stub").calls == 0  # never ran on assumed success


def test_observation_stage_summarizes_result():
    _, _, _, _, _, _, tracer, loop = make_world()
    tid = loop.tasks.create_task("obs")
    loop.run("obs", ["Read this file"], task_id=tid, correlation_id="s7-obs")
    stages = tracer.get("s7-obs").as_dict()["stages"]
    assert "observation" in stages
    entry = stages["observation"][0]
    assert entry["step_id"] == "step-1" and "summary" in entry


# ---------- Phase 4: bounded replan ----------

def test_successful_replan_recovers():
    world = make_world(extra_abilities=[FlapOnceAbility()])
    abilities, _, registry, _, _, _, tracer, loop = world
    registry.register_provider("FILE_READ", "tool", "flap-once",
                               ability_manager=abilities)
    abilities.get("files-stub").disable()
    try:
        report = loop.run("recover", ["Read this file"], correlation_id="s7-recover")
    finally:
        abilities.get("files-stub").enable()
    assert report["status"] == "completed"
    assert report["replans"] == 1
    assert "replan" in tracer.get("s7-recover").as_dict()["stages"]


def test_exhausted_replans_terminate():
    _, _, _, _, _, _, _, loop = make_world(
        extra_abilities=[AlwaysFailAbility()], max_replans=2)
    abilities = loop.matcher.abilities
    abilities.get("files-stub").disable()
    abilities.get("calc-stub").disable()
    loop.matcher.registry.register_provider("FILE_READ", "tool", "always-fail",
                                            ability_manager=abilities)
    try:
        report = loop.run("doomed", ["Read this file"], correlation_id="s7-doomed")
    finally:
        abilities.get("files-stub").enable()
        abilities.get("calc-stub").enable()
    assert report["status"] == "failed"
    assert report["replans"] == 2  # bounded, never infinite
    # Bounded attempts: initial + one execution per replan generation,
    # each capped by per-step retries (default max_retries=1 → ≤2 calls).
    assert abilities.get("always-fail").calls <= 3 * (1 + loop.max_step_retries)


def test_time_budget_exhausted():
    _, _, _, _, _, _, _, loop = make_world()
    tid = loop.tasks.create_task("slow")
    report = loop.run("slow", ["Read this file"], task_id=tid,
                      correlation_id="s7-budget", time_budget_s=0)
    assert report["status"] == "failed"
    assert any("budget" in str(f.get("reason", "")) for f in report["failed"])


def test_step_retry_policy_injected_and_capped():
    _, _, _, _, _, _, _, loop = make_world(
        extra_abilities=[AlwaysFailAbility()], max_step_retries=0)
    abilities = loop.matcher.abilities
    abilities.get("files-stub").disable()
    abilities.get("calc-stub").disable()
    loop.matcher.registry.register_provider("FILE_READ", "tool", "always-fail",
                                            ability_manager=abilities)
    try:
        report = loop.run("capped", ["Read this file"], correlation_id="s7-cap")
    finally:
        abilities.get("files-stub").enable()
        abilities.get("calc-stub").enable()
    # max_retries=0 -> exactly one attempt per execution generation
    # (initial + one per replan, replans bounded by max_replans=2).
    assert report["status"] == "failed"
    assert abilities.get("always-fail").calls == 3


def test_replan_classification_recorded():
    _, _, _, _, _, _, tracer, loop = make_world(
        extra_abilities=[AlwaysFailAbility()], max_replans=1)
    abilities = loop.matcher.abilities
    abilities.get("files-stub").disable()
    abilities.get("calc-stub").disable()
    loop.matcher.registry.register_provider("FILE_READ", "tool", "always-fail",
                                            ability_manager=abilities)
    try:
        loop.run("classy", ["Read this file"], correlation_id="s7-classy")
    finally:
        abilities.get("files-stub").enable()
        abilities.get("calc-stub").enable()
    entries = tracer.get("s7-classy").as_dict()["stages"]["replan"]
    assert entries and "failure_category" in entries[0] and "failure_code" in entries[0]


# ---------- Phase 7/8: goals + persistence ----------

def test_goal_lifecycle():
    goals = GoalManager()
    gid = goals.add("do thing", priority=5, dependencies=[])
    assert goals.get(gid)["status"] == "QUEUED"
    assert goals.activate(gid) is True
    assert goals.queued_goals() == []
    assert len(goals.active_goals()) == 1
    gid2 = goals.add("later", dependencies=[gid])
    assert goals.dependencies_met(gid2) is False
    assert goals.complete(gid) is True
    assert goals.dependencies_met(gid2) is True
    assert goals.pause(gid2) is True
    assert goals.cancel(gid2) is True
    assert goals.cancelled_goals() and not goals.active_goals()
    gid3 = goals.add("oops")
    goals.activate(gid3)
    assert goals.fail(gid3, "boom") is True
    assert goals.failed_goals()


def test_goal_legacy_helpers_compatible():
    goals = GoalManager()
    goals.add_goal("legacy")
    assert len(goals.active_goals()) == 1
    goals.complete_goal(0)
    assert len(goals.completed_goals()) == 1
    assert goals.active_goals() == []


def test_task_interruption_pause_resume():
    tasks = TaskManager()
    tid = tasks.create_task("interrupt me")
    tasks.queue_task(tid)
    tasks.start(tid)
    assert str(tasks.status(tid)) == "RUNNING"
    tasks.pause(tid)
    assert str(tasks.status(tid)) == "PAUSED"
    tasks.resume(tid)
    assert str(tasks.status(tid)) == "RUNNING"
    tasks.complete(tid)
    assert str(tasks.status(tid)) == "COMPLETED"


def test_process_restart_resume_skips_verified(tmp_path):
    store = str(tmp_path / "tasks.json")
    tm1 = TaskManager(storage_path=store)
    tid = tm1.create_task("restart me")
    tm1.queue_task(tid)
    tm1.start(tid)
    task = tm1.get(tid)
    task.setdefault("metadata", {})["capability_states"] = {
        "step-1": {"status": "completed", "required_capabilities": ["FILE_READ"],
                   "selected_tool": {"kind": "tool", "name": "files-stub"},
                   "verification": {"passed": True}},
    }
    tm1.save()
    # Simulated restart: fresh manager over the same store.
    tm2 = TaskManager(storage_path=store)
    assert str(tm2.status(tid)) in ("RUNNING", "QUEUED")
    assert "step-1" in (tm2.get(tid).get("metadata", {}).get("capability_states", {}))

    policy = PolicyManager()
    abilities = AbilityManager(policy)
    echo = EchoAbility("files-stub")
    abilities.register(echo)
    registry = CapabilityRegistry()
    registry.register_provider("FILE_READ", "tool", "files-stub",
                               ability_manager=abilities)
    matcher = ToolMatcher(abilities, policy, None, registry)
    loop = AutonomousLoop(Planner(), matcher, tm2, Tracer())
    report = loop.run("restart me", ["Read this file", "Read this file again"],
                      task_id=tid, correlation_id="s7-restart")
    assert report["status"] == "completed"
    assert echo.calls == 1  # step-1 skipped (verified), step-2 ran once


def test_duplicate_execution_prevented_on_replay():
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    echo = EchoAbility("files-stub")
    abilities.register(echo)
    registry = CapabilityRegistry()
    registry.register_provider("FILE_READ", "tool", "files-stub",
                               ability_manager=abilities)
    matcher = ToolMatcher(abilities, policy, None, registry)
    tasks = TaskManager()
    loop = AutonomousLoop(Planner(), matcher, tasks, Tracer())
    tid = tasks.create_task("once")
    first = loop.run("once", ["Read this file"], task_id=tid, correlation_id="s7-d1")
    assert first["status"] == "completed" and echo.calls == 1
    # Same task re-run: verified steps are skipped, never double-executed.
    second = loop.run("once", ["Read this file"], task_id=tid, correlation_id="s7-d2")
    assert second["skipped"] == ["step-1"]
    assert echo.calls == 1


# ---------- Phase 5: experience-aware planning ----------

def test_experience_preferred_selection():
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    first = EchoAbility("first-choice", result="A")
    second = EchoAbility("second-choice", result="B")
    abilities.register(first)
    abilities.register(second)
    registry = CapabilityRegistry()
    registry.register_provider("FILE_READ", "tool", "first-choice",
                               ability_manager=abilities)
    registry.register_provider("FILE_READ", "tool", "second-choice",
                               ability_manager=abilities)
    matcher = ToolMatcher(abilities, policy, None, registry)
    step = {"step_id": "step-1", "description": "Read this file",
            "required_capabilities": ["FILE_READ"],
            "verification_criteria": ["content returned"], "risk": "LOW"}
    selection = matcher.match(step, preferred={"FILE_READ": "second-choice"})
    assert selection.selected.name == "second-choice"


def test_experience_retrieval_and_lesson():
    manager = ExperienceManager()
    assert manager.find_relevant("create file please") == []
    record = manager.record_rich(
        "create a file", capabilities=["FILE_WRITE"], abilities=["files"],
        verification={"passed_steps": 1}, status="completed", task_id="t1")
    assert record.outcome == "SUCCESS"
    found = manager.find_relevant("create another file")
    assert found and "files" in found[0].lesson


# ---------- Phase 6/11/12: consciousness, goals, self-evaluation ----------

def test_consciousness_extended_states():
    from brain.consciousness import Consciousness, VALID_STATES
    for state in ("LISTENING", "UNDERSTANDING", "OBSERVING", "WAITING", "COMPLETED"):
        assert state in VALID_STATES
    consciousness = Consciousness()
    consciousness.set_state("ACTIVE", "test")
    consciousness.set_state("LISTENING", "test")
    consciousness.set_state("UNDERSTANDING", "test")
    consciousness.set_state("PLANNING", "test")
    consciousness.set_state("EXECUTING", "test")
    consciousness.set_state("OBSERVING", "test")
    consciousness.set_state("VERIFYING", "test")
    consciousness.set_state("REFLECTING", "test")
    consciousness.set_state("COMPLETED", "test")
    consciousness.set_state("ACTIVE", "test")
    assert consciousness.get_state() == "ACTIVE"
    with pytest.raises(ValueError):
        consciousness.set_state("DAYDREAMING")


def test_self_evaluation_structure():
    evaluator = SelfEvaluator()
    report = evaluator.evaluate_task({
        "status": "completed", "completed": ["step-1", "step-2"],
        "failed": [], "replans": 1,
        "verification": {"passed_steps": 2}})
    assert report["goal_satisfied"] is True
    assert report["steps_verified"] == 2
    assert report["replans"] == 1
    assert report["recovered"] is True
    assert report["lesson"]
    failed_eval = evaluator.evaluate_task({
        "status": "failed", "completed": [], "failed": [{"reason": "boom"}],
        "replans": 2, "verification": {"passed_steps": 0}})
    assert failed_eval["goal_satisfied"] is False
    assert failed_eval["recovery_required"] is True
    assert "boom" in failed_eval["lesson"]


def test_brain_multistep_goal_lifecycle_and_traces(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    result = brain.run_cycle("calculate 2 + 2 then calculate 3 * 3")
    assert result["status"] == "completed"
    assert result["result"]["completed"] == ["step-1", "step-2"]
    assert "goal_id" in result and "evaluation" in result
    assert result["evaluation"]["goal_satisfied"] is True
    assert brain.goals.get(result["goal_id"])["status"] == "COMPLETED"
    states = [h["state"] for h in brain.consciousness.state_history]
    for expected in ("UNDERSTANDING", "PLANNING", "EXECUTING", "OBSERVING",
                     "VERIFYING", "REFLECTING", "COMPLETED"):
        assert expected in states, expected
    ordered = [s for s in states if s in
               ("UNDERSTANDING", "PLANNING", "EXECUTING", "OBSERVING",
                "VERIFYING", "REFLECTING", "COMPLETED")]
    assert ordered == sorted(ordered, key=lambda s: (
        "UNDERSTANDING", "PLANNING", "EXECUTING", "OBSERVING",
        "VERIFYING", "REFLECTING", "COMPLETED").index(s))
    trace = brain._tracer.get(result["correlation_id"]).as_dict()["stages"]
    for stage in ("intent", "goal", "memory_retrieval", "plan", "step",
                  "capability_resolution", "ability", "permission",
                  "execution", "observation", "verification",
                  "reflection", "experience", "memory_write", "completion"):
        assert stage in trace, stage


def test_brain_failed_goal_recorded_and_evaluated(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.policy.set_permission("MATH", False)
    try:
        result = brain.run_cycle("calculate 999 + 1")
    finally:
        orch.abilities.policy.set_permission("MATH", True)
    assert result["status"] == "failed"
    assert brain.goals.get(result["goal_id"])["status"] == "FAILED"
    assert result["evaluation"]["goal_satisfied"] is False


def test_permission_rejection_blocks_multistep_dependents(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.policy.set_permission("FILE_WRITE", False)
    try:
        result = brain.run_cycle(
            "write the file notes.txt then read notes.txt",
            steps=[{"description": "write the file notes.txt",
                    "required_capabilities": ["FILE_WRITE"]},
                   {"description": "read notes.txt",
                    "required_capabilities": ["FILE_READ"],
                    "dependencies": ["step-1"]}])
    finally:
        orch.abilities.policy.set_permission("FILE_WRITE", True)
    # Permission failure fails fast at validation: nothing executes, so no
    # dependent can run on assumed success and no file is created.
    assert result["status"] == "failed"
    from pathlib import Path
    assert not Path("notes.txt").exists()
    blob = str(result.get("result", "")) + str(result.get("error", ""))
    assert "permission" in blob.lower() or "PERMISSION" in blob


def test_high_risk_requires_explicit_approval():
    policy = PolicyManager()
    abilities = AbilityManager(policy)
    abilities.register(HighRiskAbility())
    with pytest.raises(RuntimeError, match="pproval"):
        abilities.execute("danger-stub", "do it", capabilities=["TERMINAL_EXECUTE"])
    assert abilities.get("danger-stub").calls == 0
    outcome = abilities.execute("danger-stub", "do it",
                                capabilities=["TERMINAL_EXECUTE"],
                                approval_required=True, approved=True)
    assert outcome["status"] == "success"


def test_infinite_loops_impossible_by_construction():
    _, _, _, _, _, _, _, loop = make_world(
        extra_abilities=[AlwaysFailAbility()], max_replans=2)
    abilities = loop.matcher.abilities
    for name in ("files-stub", "calc-stub"):
        abilities.get(name).disable()
    loop.matcher.registry.register_provider("FILE_READ", "tool", "always-fail",
                                            ability_manager=abilities)
    try:
        report = loop.run("loop?", ["Read this file"], correlation_id="s7-loop")
    finally:
        for name in ("files-stub", "calc-stub"):
            abilities.get(name).enable()
    assert report["status"] == "failed"
    assert report["replans"] <= 2
    # Bounded attempts overall: initial + at most max_replans replans,
    # each capped by per-step retries.
    assert abilities.get("always-fail").calls <= 3 * (1 + loop.max_step_retries)
    assert abilities.get("always-fail").calls >= 1


def _load_boot_module():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "hercule_boot", str(Path("boot.py").resolve()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conversation_stays_out_of_autonomy(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    boot = _load_boot_module()
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    cli = boot.HerculeCli(services["brain"])
    before = len(services["orchestrator"].task_manager)
    for line in ("hi", "what is your name"):
        result = cli.handle_line(line)
        assert result["kind"] == "QUESTION"
    assert len(services["orchestrator"].task_manager) == before
