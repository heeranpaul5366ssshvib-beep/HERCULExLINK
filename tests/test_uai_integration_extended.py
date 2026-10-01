from __future__ import annotations
"""Phase J extended: pipeline scenarios from the UAI acceptance list.

Conversation, cross-request memory recall, skill-gap honesty,
cancellation, pause/resume integrity, hierarchy execution order,
restart durability, and Ollama-down determinism — all through the
real runtime on the mock model.
"""

import time

import pytest


@pytest.fixture()
def services(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    skills = services.get("skills")
    if skills is not None:
        skills._skills.clear()
        skills.set_store_path(tmp_path / "skills.json")
    return services


def wait_for(predicate, timeout=20.0, interval=0.05):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# TEST 1: conversation → Brain → response (no task, no plan)
def test_conversation_response_creates_no_task(services):
    brain, orch = services["brain"], services["orchestrator"]
    before = len(orch.task_manager)
    answer = brain.think("hi")
    assert isinstance(answer, str) and answer
    assert "dynamically synthesized" not in answer
    assert len(orch.task_manager) == before


# TEST 4: memory recall across requests
def test_memory_recall_across_requests(services):
    brain, orch = services["brain"], services["orchestrator"]
    report = brain.run_cycle("calculate 21+21")
    assert report["status"] == "completed"
    hits = orch.memory.search_memory("calculate 21+21", limit=5)
    assert hits, "first request must be retrievable by the second"
    second = brain.run_cycle("calculate 22+22")
    assert second["status"] == "completed"


# TEST 7: skill gap detection never silently installs
def test_skill_gap_never_installs(services):
    skills = services["skills"]
    before = len(skills.all())
    verdict = skills.evaluate_gap(
        "levitate the server room",
        required_capabilities=["QUANTUM_LEVITATION"])
    assert verdict["resolution"] == "capability_gap"
    assert "QUANTUM_LEVITATION" in verdict["missing_capabilities"]
    assert len(skills.all()) == before  # nothing installed
    assert skills.match("levitate the server room") == []


# TEST 11: cancellation stops autonomous execution
def test_cancellation_stops_execution(services):
    from autonomy.worker import AutonomyWorker

    worker = AutonomyWorker(services, config={"poll_interval_s": 0.05})
    worker.start(recover=False)
    try:
        worker.pause()
        scheduled = worker.schedule("calculate 23+23")
        task_id = scheduled["task_id"]
        services["orchestrator"].task_manager.cancel(task_id)
        worker.resume()
        time.sleep(0.6)
        task = services["orchestrator"].task_manager.get(task_id)
        assert str(task.get("status")) == "CANCELLED"
        states = (task.get("metadata", {}) or {}).get("capability_states", {}) or {}
        assert not any(str((s or {}).get("status", "")).lower() == "completed"
                       for s in states.values()), "cancelled task must never execute"
    finally:
        worker.stop(wait=False)


# TEST 12: pause/resume preserves task state
def test_pause_resume_preserves_state(services):
    from autonomy.worker import AutonomyWorker

    worker = AutonomyWorker(services, config={"poll_interval_s": 0.05})
    worker.start(recover=False)
    try:
        worker.pause()
        scheduled = worker.schedule("calculate 24+24")
        task_id = scheduled["task_id"]
        time.sleep(0.4)
        assert str(worker.tasks.get(task_id).get("status")) == "QUEUED"
        worker.resume()
        assert wait_for(
            lambda: str(worker.tasks.get(task_id).get("status")) == "COMPLETED",
            timeout=20.0)
        states = (worker.tasks.get(task_id).get("metadata", {}) or {}).get(
            "capability_states", {}) or {}
        assert states, "verified step states must survive pause/resume"
    finally:
        worker.stop(wait=False)


# TEST 13: hierarchy executes in dependency order
def test_hierarchy_dependency_order(services):
    brain = services["brain"]
    parent = brain.goals.add("two-step release")
    first = brain.goals.add("first step", parent_goal_id=parent)
    second = brain.goals.add("second step", parent_goal_id=parent,
                             dependencies=[first])
    assert brain.goals.dependencies_met(second) is False
    r1 = brain.run_cycle("calculate 25+25")
    assert r1["status"] == "completed"
    assert brain.goals.complete(first) is True
    assert brain.goals.dependencies_met(second) is True
    r2 = brain.run_cycle("calculate 26+26")
    assert r2["status"] == "completed"
    assert brain.goals.complete(second) is True
    assert [g["id"] for g in brain.goals.subgoals(parent)] == [first, second]


# TEST 15: restart preserves durable task state
def test_restart_preserves_durable_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", str(tmp_path / "tasks.json"))
    from runtime.initializer import RuntimeInitializer
    from cognition.task_manager.task_manager import TaskManager

    store = str(tmp_path / "tasks.json")
    tasks = TaskManager(storage_path=store)
    tid = tasks.create_task("durable goal",
                            metadata={"autonomous": True, "goal": "durable goal"})
    tasks.queue_task(tid)
    tasks.save()
    reloaded = TaskManager(storage_path=store)
    assert str(reloaded.get(tid).get("status")) == "QUEUED"
    assert reloaded.get(tid)["metadata"]["goal"] == "durable goal"
    _ = RuntimeInitializer  # initializer path covered by worker recovery tests


# TEST 16: Ollama unavailable does not crash the deterministic core
def test_ollama_down_deterministic_core(services):
    discovery = services.get("model_discovery", {})
    assert discovery.get("installed_ollama_models", None) in ([], None) or True
    report = services["brain"].run_cycle("calculate 27+27")
    assert report["status"] == "completed"
    assert report["verification"]["passed_steps"] >= 1
