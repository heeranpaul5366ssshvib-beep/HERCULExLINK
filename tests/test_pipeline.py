"""Canonical Brain -> AutonomousLoop pipeline (migrated Phase K).

Previously this test asserted the legacy direct-execution path
(orchestrator.pipeline stages calling models.generate per step with no
task, policy, or verification). That path is DEPRECATED
(see Brain._execute_stage); the assertions below pin the canonical
path: durable task lifecycle + verification + memory + correlation.
"""

from runtime.initializer import RuntimeInitializer


def test_full_pipeline_records_memory_and_executes():
    init = RuntimeInitializer()
    services = init.initialize()

    brain = services["brain"]
    memory = services["memory"]
    tasks = services["orchestrator"].task_manager

    # run through the canonical autonomous path
    res = brain.run_cycle("Calculate the totals", payload_fn=lambda step: "6*7")

    # durable task completed through the lifecycle
    assert res["status"] == "completed"
    assert str(tasks.get(res["task_id"])["status"]) == "COMPLETED"

    # verification is authoritative, not "tool returned"
    assert res["verification"]["passed_steps"] >= 1

    # memory recorded the verified event
    assert len(memory.event_history()) >= 1

    # correlation survives the workflow
    assert res["correlation_id"]
    assert tasks.get(res["task_id"])["metadata"]["correlation_id"] == res["correlation_id"]
