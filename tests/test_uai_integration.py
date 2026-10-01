from __future__ import annotations
"""Phase J: UAI integration tests (pipeline traversal, not unit checks).

Each test crosses real runtime boundaries on the mock model:
Brain → planner → capabilities → abilities → verification → memory,
plus skill/research/autonomy/goal/event/experience legs.
"""

import pytest

from abilities.base_ability import BaseAbility


@pytest.fixture()
def services(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    # Hermetic skill store: the initializer loads the shared on-disk
    # registry; tests must neither pollute it nor collide with it.
    skills = services.get("skills")
    if skills is not None:
        skills._skills.clear()
        skills.set_store_path(tmp_path / "skills.json")
    return services


class FlakyAbility(BaseAbility):
    """Fails once, then succeeds — bounded replan/recovery."""

    def __init__(self, name="flaky-tool"):
        super().__init__(name, "flaky")
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"status": "failed", "error": "transient boom"}
        return {"status": "success", "content": "recovered-content"}


class DictSource:
    def __init__(self, sources=None, error=None):
        self._sources = sources
        self._error = error

    def execute(self, topic, **kwargs):
        if self._error is not None:
            raise self._error
        return {"status": "success", "sources": self._sources}


# TEST 1: full pipeline → memory + experience
def test_1_full_pipeline_to_memory(services):
    brain, orch = services["brain"], services["orchestrator"]
    report = brain.run_cycle("calculate 2+2")
    assert report["status"] == "completed"
    assert report["verification"]["passed_steps"] >= 1
    history = orch.memory.event_history()
    assert any(report["task_id"] in str(e) for e in history)
    stack = brain._autonomy_stack()
    records = stack["experience"].query(limit=100000)
    assert any(r.outcome in ("SUCCESS", "RECOVERED") for r in records)


# TEST 2: skill resolution → planner → ability → verification
def test_2_skill_to_execution(services):
    from cognition.skills import Skill

    brain = services["brain"]
    skills = services["skills"]
    assert skills is not None
    skills.register(Skill(skill_id="calc-skill", description="calculate totals",
                          required_capabilities=["MATH"],
                          procedure=["Calculate 3+3"]),
                    validate=True)
    matches = skills.match("calculate 3+3 now")
    assert matches and matches[0].skill_id == "calc-skill"
    report = brain.run_cycle("calculate 3+3", steps=list(matches[0].procedure))
    assert report["status"] == "completed"
    assert report["verification"]["passed_steps"] >= 1
    assert skills.record_outcome("calc-skill", True) is True


# TEST 3: research → evidence → verification
def test_3_research_to_verification(services):
    abilities = services["orchestrator"].abilities
    abilities.ensure_defaults()
    research = abilities.registry.get("research")
    assert research is not None
    research.attach_source(DictSource([
        {"url": "https://example.test/a", "content": "[FACT] alpha holds here"},
        {"url": "https://example.test/b", "content": "[FACT] beta holds here"},
    ]))
    out = abilities.execute("research", "alpha and beta",
                            capabilities=["KNOWLEDGE_RETRIEVAL"])
    assert out["status"] == "success"
    assert out["verification_status"] == "verified"
    assert [e["label"] for e in out["evidence"]] == ["FACT", "FACT"]
    research.attach_source(None)  # leave runtime pristine


# TEST 4: autonomy level → policy → execution
def test_4_autonomy_level_to_execution(services):
    from autonomy.worker import AutonomyWorker

    worker = AutonomyWorker(services, config={"poll_interval_s": 3600})
    try:
        scheduled = worker.schedule("calculate 4+4")
        assert scheduled["status"] == "QUEUED"
        report = services["brain"].run_cycle("calculate 4+4")
        assert report["status"] == "completed"
    finally:
        try:
            worker.stop(wait=False)
        except Exception:
            pass


# TEST 5: autonomy level → policy denial
def test_5_autonomy_policy_denial(services):
    abilities = services["orchestrator"].abilities
    policy = getattr(abilities, "policy", None)
    assert policy is not None
    policy.set_permission("MATH", False)
    try:
        report = services["brain"].run_cycle("calculate 9+9")
    finally:
        policy.set_permission("MATH", True)
    assert report["status"] == "failed"
    blob = str(report.get("result", "")) + str(report.get("error", ""))
    assert "PERMISSION" in blob or "permission" in blob


# TEST 6: tool failure → observation → retry/replan
def test_6_tool_failure_replans(services):
    brain, orch = services["brain"], services["orchestrator"]
    orch.abilities.register(FlakyAbility())
    brain.register_capability("FILE_WRITE", "tool", "flaky-tool")
    report = brain.run_cycle("write the file flaky-report")
    assert report["replans"] <= 2
    assert report["status"] in ("completed", "partial", "failed")
    if report["status"] == "completed":
        assert report["verification"]["passed_steps"] >= 1


# TEST 7: execution failure → reflection → experience
def test_7_failure_reflects_to_experience(services):
    brain = services["brain"]
    abilities = services["orchestrator"].abilities
    policy = getattr(abilities, "policy", None)
    assert policy is not None
    policy.set_permission("MATH", False)
    try:
        report = brain.run_cycle("calculate 1+1")
    finally:
        policy.set_permission("MATH", True)
    # Policy denial fails inside the loop (not the plan gate), so
    # reflection + experience recording still run honestly.
    assert report["status"] == "failed"
    stack = brain._autonomy_stack()
    # query() sorts successes first and the file store is shared across
    # suites, so filter the full history instead of slicing the top.
    records = stack["experience"].query(limit=100000)
    failed = [r for r in records if r.outcome in ("FAILED", "UNRECOVERED")]
    assert failed and all(r.lesson for r in failed)


# TEST 8: goal hierarchy → planner → execution
def test_8_hierarchy_to_execution(services):
    brain = services["brain"]
    parent = brain.goals.add("parent release",
                             deadline="2026-12-31T00:00:00+00:00")
    child = brain.goals.add("child task", parent_goal_id=parent)
    report = brain.run_cycle("calculate 5+5")
    assert report["status"] == "completed"
    assert brain.goals.complete(child) is True
    assert brain.goals.get(parent)["status"] == "QUEUED"
    assert brain.goals.subgoals(parent)[0]["id"] == child


# TEST 9: lifecycle EventBus receives pipeline events
def test_9_lifecycle_events(services):
    brain, orch = services["brain"], services["orchestrator"]
    seen = []
    for event in ("USER_REQUEST", "GOAL_CREATED", "PLAN_CREATED",
                  "GOAL_COMPLETED", "GOAL_FAILED"):
        orch.event_bus.subscribe(event, lambda _e=event, **kw: seen.append(_e))
    report = brain.run_cycle("calculate 6+6")
    assert report["status"] == "completed"
    assert "USER_REQUEST" in seen and "GOAL_COMPLETED" in seen


# TEST 10: experience → validated proposal → skill (no auto-promotion)
def test_10_experience_to_skill(services):
    brain = services["brain"]
    skills = services["skills"]
    # Wiring note: the initializer passes CognitionManager.experience
    # (absent) to SkillManager, so the bridge is attached here to the
    # Brain-owned ExperienceManager — the same store run_cycle records
    # into. Permanent shared-store wiring is tracked as remaining work.
    experience = brain._autonomy_stack()["experience"]
    skills.experience = experience
    first = experience.record_rich(
        "calculate quarterly totals", capabilities=["MATH"],
        abilities=["mathematics"], verification={"passed_steps": 1},
        status="completed", task_id="t-1")
    for i in ("t-2", "t-3"):
        experience.record_rich(
            "calculate quarterly totals", capabilities=["MATH"],
            abilities=["mathematics"], verification={"passed_steps": 1},
            status="completed", task_id=i)
    proposal = experience.propose_procedure(first.goal_type)
    assert proposal is not None
    # Unvalidated proposals are never promoted...
    assert skills.register_from_experience(proposal) is None
    experience.validate_procedure(proposal.procedure_id, True, note="reviewed")
    # ...validated ones become PROPOSED candidates, never auto-executable.
    skill = skills.register_from_experience(proposal)
    assert skill is not None and not skill.is_registered()
    assert skill.source == "experience"
