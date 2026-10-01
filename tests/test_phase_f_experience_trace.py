"""Phase F: experience engine, traces/diagnostics, resources, integration."""

from cognition.experience.experience_manager import ExperienceManager
from cognition.task_manager.task_manager import TaskManager
from memory.memory_manager import MemoryManager
from memory.vector.vector_manager import VectorMemory
from models.adapters.mock_adapter import MockAdapter
from system.observability.trace import (
    Tracer,
    explain_memory_retrieval,
    explain_model_selection,
    explain_retry,
    explain_tool_selection,
    explain_verification_failure,
)
from system.resources import resource_snapshot, under_pressure


def _completed_task(manager: TaskManager, description: str, result: str = "done") -> dict:
    tid = manager.create_task(description)
    manager.queue_task(tid)
    manager.start(tid)
    manager.complete(tid, result=result)
    return manager.get(tid)


def test_experience_distills_tasks_without_raw_logs():
    manager = TaskManager()
    task = _completed_task(manager, "Diagnose common project dependency failures")
    experience = ExperienceManager()
    record = experience.record_from_task(task)
    assert record.goal_type == "diagnosis"
    assert record.success == 1.0
    assert record.task_id == task["id"]
    assert record.recorded_at
    assert "history" not in record.as_dict()  # distilled, not raw logs


def test_failed_task_experience_keeps_failures():
    manager = TaskManager()
    tid = manager.create_task("Repair adapter")
    manager.queue_task(tid)
    manager.start(tid)
    manager.fail(tid, "tool timeout")
    experience = ExperienceManager()
    record = experience.record_from_task(manager.get(tid))
    assert record.success == 0.0
    assert record.failures == ["tool timeout"]


def test_procedure_promotion_requires_repeated_success():
    experience = ExperienceManager(min_samples_for_procedure=3)
    manager = TaskManager()
    one = _completed_task(manager, "Diagnose router fault A")
    experience.record_from_task(one)
    assert experience.propose_procedure("diagnosis") is None  # anecdote, not evidence
    for desc in ("Diagnose router fault B", "Diagnose router fault C"):
        experience.record_from_task(_completed_task(manager, desc))
    proposal = experience.propose_procedure("diagnosis")
    assert proposal is not None
    assert proposal.validated is False
    assert len(proposal.supporting_experiences) == 3
    assert proposal.success_rate >= 0.8
    validated = experience.validate_procedure(proposal.procedure_id, True, "reviewed")
    assert validated.validated is True
    assert experience.validate_procedure("nope", True) is None
    assert experience.query(goal_type="diagnosis", min_success=0.9)
    assert experience.statistics()["experiences"] == 3


def test_tracer_threads_correlation_across_stages():
    tracer = Tracer()
    tracer.record("corr-9", "request", {"prompt": "fix router"})
    tracer.record("corr-9", "retrieval", {"strategy": "hybrid", "hits": 3})
    tracer.record("corr-9", "model_selection", {"model": "mock"})
    snapshot = tracer.snapshot()
    assert set(snapshot["corr-9"]["stages"]) == {"request", "retrieval", "model_selection"}
    assert tracer.get("missing") is None


def test_diagnostic_explainers_answer_five_whys():
    result = explain_model_selection({"model": "mock", "reason": "best available", "adapter_name": "mock"})
    assert result["answer"] == "best available"
    assert result["evidence"]["model"] == "mock"
    memory_answer = explain_memory_retrieval({"correlation_id": "c", "items": [{"source": "memory"}, {"source": "knowledge"}]})
    assert "memory" in memory_answer["answer"]
    manager = TaskManager()
    tid = manager.create_task("Task with tool", tool="shell")
    assert explain_tool_selection(manager.get(tid))["evidence"]["plan"] == []
    manager.queue_task(tid)
    manager.start(tid)
    manager.fail(tid, "boom")
    manager.retry(tid, reason="flaky network")
    assert "flaky" in explain_retry(manager.get(tid))["answer"]
    tid2 = manager.create_task("Verify me", expected_result="x")
    manager.queue_task(tid2)
    manager.start(tid2)
    try:
        manager.verify(tid2, "y")
    except ValueError:
        pass
    assert "expected" in explain_verification_failure(manager.get(tid2))["answer"]


def test_resource_snapshot_is_honest():
    snapshot = resource_snapshot()
    assert set(snapshot) >= {"cpu_percent", "ram_percent", "ram_available_mb", "disk_percent", "source"}
    assert under_pressure(snapshot) is False or snapshot["source"] == "psutil"
    assert under_pressure({"source": "unavailable", "cpu_percent": 99.0}) is False
    assert under_pressure({"source": "psutil", "cpu_percent": 99.0, "ram_percent": 10.0}) is True


def test_memory_vector_roundtrip_and_clear():
    manager = MemoryManager()
    vector = MockAdapter()._text_to_vector("router health")  # dim 64 matches the default store
    manager.store_vector("router-doc", vector, {"source": "test"})
    record = manager.retrieve_vector("router-doc")
    assert record is not None and record["text"] == "router-doc"
    assert manager.retrieve_vector("absent") is None
    VectorMemory().clear()  # must not crash on either backend


def test_end_to_end_grounded_answer_flow():
    """QUERY -> RETRIEVE -> EVIDENCE -> CONTEXT stays connected."""
    from knowledge.evidence import ground_answer
    from knowledge.knowledge_manager import KnowledgeManager

    knowledge = KnowledgeManager()
    knowledge.ingest_document("router.md", "The model router selects adapters by health. " * 8, source="unit-test")
    hits = knowledge.hybrid_retrieve("which component selects adapters", top_k=3)
    assert hits
    grounded = ground_answer(["The model router selects adapters"], hits)
    assert grounded[0]["evidence"]["chunk_id"] == hits[0]["chunk_id"]
