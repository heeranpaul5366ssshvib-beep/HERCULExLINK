"""Stage 5: persistent memory + experience learning tests.

Covers: creation, persistence, retrieval, update, deletion, dedup,
corrupt recovery, experience recording (success/failure), retrieval,
experience-aware planning, explicit user memory, restart survival,
no-CoT persistence, irrelevant filtering.
"""
import json

import pytest

from cognition.experience.experience_manager import ExperienceManager
from memory.memory_manager import MemoryManager
from memory.persistence import MemoryRecord, PersistentStore


@pytest.fixture()
def store_path(tmp_path, monkeypatch):
    target = tmp_path / "memory" / "hercule_memory.json"
    monkeypatch.setenv("HERCULE_MEMORY_DIR", str(tmp_path / "memory"))
    return target


@pytest.fixture()
def memory(store_path):
    return MemoryManager()


def test_1_memory_creation(memory):
    stored = memory.remember_fact("project", "my project is called HERCULE")
    assert stored["content"] == "my project is called HERCULE"
    assert memory.recall_fact("project") == "my project is called HERCULE"


def test_2_memory_persistence(memory, store_path):
    memory.remember_fact("language", "I prefer Java")
    assert store_path.exists()
    data = json.loads(store_path.read_text(encoding="utf-8"))
    assert any(r["memory_type"] == "semantic" for r in data["records"])


def test_3_memory_retrieval(memory):
    memory.remember_fact("project", "my project is called HERCULE")
    hits = memory.search_memory("project called HERCULE", memory_type="semantic")
    assert hits and hits[0]["record"]["content"] == "my project is called HERCULE"


def test_4_memory_update(memory):
    memory.remember_fact("project", "project v1")
    memory.remember_fact("project", "project v2")
    assert memory.recall_fact("project") == "project v2"


def test_5_memory_deletion(memory):
    memory.remember_fact("project", "temporary fact")
    assert memory.forget_fact("project") is True
    assert memory.recall_fact("project") is None


def test_6_duplicate_prevention(memory):
    memory.remember_fact("project", "same fact")
    memory.remember_fact("project", "same fact")
    records = [r for r in memory.store.all("semantic")
               if r.content == "same fact"]
    assert len(records) == 1


def test_7_corrupted_storage_recovery(tmp_path, monkeypatch):
    directory = tmp_path / "memory"
    directory.mkdir()
    target = directory / "hercule_memory.json"
    target.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("HERCULE_MEMORY_DIR", str(directory))
    recovered = MemoryManager()  # must not raise
    assert recovered.recall_fact("anything") is None
    assert list(directory.glob("*.bak"))  # corrupt file backed up


def test_8_experience_recording_success():
    manager = ExperienceManager()
    record = manager.record_rich("create a file", capabilities=["FILE_WRITE"],
                                 abilities=["files"],
                                 verification={"passed_steps": 1},
                                 status="completed", task_id="t1")
    assert record.outcome == "SUCCESS"
    assert "files" in record.lesson and "FILE_WRITE" in record.lesson


def test_8b_experience_outcomes():
    manager = ExperienceManager()
    assert manager.record_rich("g", status="completed", task_id="a").outcome == "SUCCESS"
    assert manager.record_rich("g", status="completed", replans=1, task_id="b").outcome == "RECOVERED"
    assert manager.record_rich("g", status="partial", task_id="c").outcome == "PARTIAL"
    assert manager.record_rich("g", status="failed", task_id="d").outcome == "FAILED"
    rec = manager.record_rich("g", status="failed", replans=2,
                              failure_reason="boom", task_id="e")
    assert rec.outcome == "UNRECOVERED" and "boom" in rec.lesson


def test_9_successful_experience_retrieval():
    manager = ExperienceManager()
    manager.record_rich("create a text file", capabilities=["FILE_WRITE"],
                        abilities=["files"], status="completed", task_id="t1")
    found = manager.find_relevant("create another file")
    assert found and found[0].outcome == "SUCCESS"


def test_10_failed_experience_retrieval():
    manager = ExperienceManager()
    manager.record_rich("write report", capabilities=["FILE_WRITE"],
                        abilities=["fail-tool"], status="failed",
                        failure_reason="boom", task_id="t9")
    found = manager.find_relevant("write report", outcome="failed")
    assert found and "boom" in found[0].lesson
    assert manager.find_relevant("unrelated zebra quantum") == []


def test_11_experience_aware_planning(store_path):
    import os
    os.environ.setdefault("HERCULE_MEMORY_DIR", str(store_path.parent))
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    first = brain.run_cycle("calculate 6 * 7")
    assert first["status"] == "completed"
    relevant = brain.relevant_experiences("calculate 3 * 3")
    assert relevant and relevant[0]["outcome"] in ("SUCCESS", "RECOVERED")
    assert "MATH" in relevant[0]["capabilities"]
    second = brain.run_cycle("calculate 3 * 3")
    assert second["status"] == "completed"
    trace = brain._tracer.get(second["correlation_id"]).as_dict()["stages"]
    assert "memory_retrieval" in trace
    assert "experience" in trace and "memory_write" in trace


def test_12_explicit_user_memory(store_path):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "hercule_boot_mem", str(Path("boot.py").resolve()))
    boot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boot)
    services = boot.initialize_runtime()
    cli = boot.HerculeCli(services["brain"])
    assert boot.classify_request("remember that my project is called HERCULE") == "MEMORY"
    saved = cli.handle_line("remember that my project is called HERCULE")
    assert saved["kind"] == "MEMORY" and saved["status"] == "remembered"
    asked = cli.handle_line("what do you remember about my project?")
    assert asked["kind"] == "MEMORY"
    assert "HERCULE" in asked["response"]
    # No task lifecycle for memory directives.
    assert "task_id" not in asked


def test_13_memory_survives_restart(store_path):
    from runtime.initializer import RuntimeInitializer
    first = RuntimeInitializer().initialize()
    first["brain"].remember_fact("remember that my project is called HERCULE")
    assert store_path.exists()
    second = RuntimeInitializer().initialize()  # simulated restart
    assert second["memory"].recall_fact("project") is not None
    assert "HERCULE" in second["memory"].recall_fact("project")


def test_14_no_chain_of_thought_persistence(store_path):
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    brain.think("hi there")
    brain.run_cycle("calculate 2 + 2")
    blob = store_path.read_text(encoding="utf-8").lower()
    for marker in ("chain-of-thought", "hidden reasoning", "system prompt"):
        assert marker not in blob


def test_15_irrelevant_memory_filtering(memory):
    memory.remember_fact("project", "my project is called HERCULE")
    assert memory.search_memory("zebra quantum banana", memory_type="semantic") == []
