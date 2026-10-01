from __future__ import annotations
"""Advanced memory tests (v2 Phase 3).

Covers: creation, retrieval, relevance ranking, recency, importance,
confidence, deduplication, retention, consolidation, procedural
learning, correction, forgetting, explicit memory, experience
retrieval, task synchronization, world-model separation, restart
persistence, corrupted storage, no-CoT storage, secrets redaction,
embedder gating, UI/HUD snapshot, bounded Brain context. Isolated
store paths (tmp) throughout.
"""

import json
import time

import pytest

from memory.memory_manager import MemoryManager, redact_secrets
from memory.persistence import PersistentStore


def _manager(tmp_path, name="memory.json"):
    return MemoryManager(store_path=str(tmp_path / name))


# --------------------------------------------------
# creation / retrieval / evidence
# --------------------------------------------------
def test_creation_and_evidence(tmp_path):
    memory = _manager(tmp_path)
    stored = memory.remember_fact("lang", "project uses Python")
    assert stored["content"] == "project uses Python"
    assert stored["id"] and stored.get("superseded") == 0
    hits = memory.retrieve_relevant("project language Python")
    assert hits and hits[0]["record"]["content"] == "project uses Python"
    assert "lexical" in hits[0]["layers"]
    assert set(hits[0]["evidence"]) >= {"source", "memory_type", "timestamp"}


def test_relevance_ranking_exact_beats_generic(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_fact("other", "unrelated cooking recipe")
    memory.remember_fact("lang", "project uses Python")
    hits = memory.retrieve_relevant("lang Python")
    assert hits[0]["record"]["content"] == "project uses Python"
    assert "metadata" in hits[0]["layers"]


def test_recency_and_importance_factors(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_fact("a", "shared token alpha one")
    time.sleep(0.05)
    memory.remember_fact("b", "shared token alpha two")
    hits = memory.retrieve_relevant("shared token alpha")
    assert hits[0]["record"]["content"] == "shared token alpha two"
    assert hits[0]["factors"]["recency"] >= hits[1]["factors"]["recency"]
    memory.remember_fact("c", "shared token alpha three", importance=0.1)
    assert memory.retrieve_relevant("shared token alpha")[0]["factors"][
        "importance"] >= 0.8


def test_confidence_recorded_not_hidden(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_fact("guess", "maybe the port is 8080", importance=0.3)
    hits = memory.retrieve_relevant("port 8080")
    assert hits and hits[0]["factors"]["confidence"] == 1.0


# --------------------------------------------------
# deduplication / retention
# --------------------------------------------------
def test_deduplication_no_unbounded_copies(tmp_path):
    memory = _manager(tmp_path)
    for _ in range(5):
        memory.remember_fact("dup", "same thing")
    assert len([r for r in memory.store.all("semantic")
                if r.content == "same thing"]) == 1


def test_retention_protects_explicit_facts(tmp_path):
    store = PersistentStore(str(tmp_path / "m.json"),
                            retention_caps={"semantic": 3})
    for i in range(5):
        from memory.persistence import MemoryRecord

        store.put(MemoryRecord(memory_type="semantic", source="task",
                               content=f"trivial {i}", importance=0.1))
    from memory.persistence import MemoryRecord

    store.put(MemoryRecord(memory_type="semantic", source="user",
                           content="explicit keeper", tags=["fact"],
                           importance=0.9,
                           metadata={"topic": "keep"}))
    store.save()
    assert any(r.content == "explicit keeper" for r in store.all("semantic"))
    assert len(store.all("semantic")) <= 4  # cap + protected explicit


# --------------------------------------------------
# consolidation / procedural learning
# --------------------------------------------------
def test_consolidation_promotes_repeats(tmp_path):
    memory = _manager(tmp_path)
    for i in range(3):
        memory.remember_event({"task_id": f"t{i}", "status": "COMPLETED",
                               "metadata": {"goal": "nightly backup"}})
    receipt = memory.consolidate()
    assert receipt["promoted"] == 1
    assert memory.consolidate()["promoted"] == 0  # idempotent
    assert any("nightly backup" in r.content
               for r in memory.store.all("semantic"))


def test_experience_promotes_procedure(tmp_path):
    memory = _manager(tmp_path)
    exps = [{"outcome": "SUCCESS", "capabilities": ["FILE_WRITE", "FILE_READ"],
             "lesson": "write then verify"},
            {"outcome": "SUCCESS", "capabilities": ["FILE_READ", "FILE_WRITE"],
             "lesson": "write then verify"},
            {"outcome": "FAILED", "capabilities": ["FILE_WRITE"],
             "lesson": "ignored"}]
    assert memory.consolidate(experiences=exps)["procedures"] == 1
    assert memory.procedures_for("file") != []
    assert memory.execute_skill("workflow:file_read+file_write")["advisory"] is True
    assert memory.promote_procedure("demo", ["a", "b"]) is True
    assert memory.promote_procedure("", []) is False


def test_experience_retrieval_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    assert brain.relevant_experiences("anything at all", limit=2) == []
    ctx = brain.build_brain_context("hello there")
    assert isinstance(ctx, str) and len(ctx) <= 1500


# --------------------------------------------------
# correction / forgetting / explicit
# --------------------------------------------------
def test_correction_supersedes_history_kept(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_fact("lang", "project uses Python")
    stored = memory.remember_fact("lang", "project uses Java")
    assert stored.get("superseded") == 1
    assert memory.recall_fact("lang") == "project uses Java"
    assert "Java" in memory.retrieve_relevant("project language")[0]["record"]["content"]
    tombstones = [r for r in memory.store.all("semantic")
                  if (r.metadata or {}).get("invalidated")]
    assert any("Python" in r.content for r in tombstones)  # history kept


def test_forgetting_invalidates_but_keeps_history(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_fact("temp", "temporary value")
    assert memory.forget_fact("temp") is True
    assert memory.recall_fact("temp") is None
    assert memory.facts().get("temp") is None
    assert memory.retrieve_relevant("temporary value") == []
    assert any((r.metadata or {}).get("invalidated")
               for r in memory.store.all("semantic"))
    assert memory.forget_fact("missing-topic") is False


def test_explicit_memories_api(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_fact("a", "alpha")
    memory.remember_fact("b", "beta")
    assert memory.explicit_memories() == {"a": "alpha", "b": "beta"}
    assert memory.memories_about("alpha")[0]["record"]["content"] == "alpha"


# --------------------------------------------------
# task synchronization via TaskManager events
# --------------------------------------------------
def test_task_events_sync_memory_and_world(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_WORLD_PATH", str(tmp_path / "world.json"))
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    tasks = services["orchestrator"].task_manager
    task_id = tasks.create_task("sync probe goal")
    tasks.start(task_id)
    tasks.complete(task_id, result={"ok": True})
    memory = services["memory"]
    assert any(task_id in str(e) for e in
               [m["content"] for m in memory.history_snapshot(limit=20)]
               + [str(r) for r in memory.event_history()])
    world = services["brain"].world
    assert any(e.properties.get("task_id") == task_id
               for e in world.repo.entities.values() if e.type == "task")
    mems = memory.memories_for_task(task_id)
    assert mems and mems[0]["evidence"]["source"] == "task"


# --------------------------------------------------
# world-model separation
# --------------------------------------------------
def test_world_state_beats_stale_memory_for_present(tmp_path):
    from world.model import WorldModel

    memory = _manager(tmp_path)
    world = WorldModel(path=str(tmp_path / "world.json"))
    memory.remember_fact("app", "notepad was running yesterday")
    world.observe_application("notepad", "closed", evidence="window gone",
                              verified=True)
    assert world.repo.get("application:notepad").properties["state"] == "closed"
    assert any("yesterday" in r.content for r in memory.store.all("semantic"))


# --------------------------------------------------
# restart / corruption / bounds / no-CoT
# --------------------------------------------------
def test_restart_persistence_and_rehydrate(tmp_path):
    path = str(tmp_path / "memory.json")
    first = MemoryManager(store_path=path)
    first.remember_fact("lang", "project uses Python")
    second = MemoryManager(store_path=path)
    assert second.recall_fact("lang") == "project uses Python"
    assert second.facts()["lang"] == "project uses Python"


def test_corrupt_storage_recovers(tmp_path):
    target = tmp_path / "memory.json"
    target.write_text("{broken", encoding="utf-8")
    memory = MemoryManager(store_path=str(target))
    assert memory.recall_fact("x") is None
    assert list(tmp_path.glob("*.bak"))
    assert memory.save() is True


def test_no_chain_of_thought_stored(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_event({"task_id": "t", "status": "COMPLETED",
                           "metadata": {"goal": "x" * 5000}})
    memory.remember_fact("long", "y" * 5000)
    for record in memory.store.all():
        assert len(record.content) <= 2000
        assert "chain-of-thought" not in record.content.lower()


# --------------------------------------------------
# secrets redaction
# --------------------------------------------------
def test_secrets_never_persisted(tmp_path):
    assert "[REDACTED]" in redact_secrets("password: hunter2")
    assert "hunter2" not in redact_secrets("password: hunter2")
    assert "[REDACTED]" in redact_secrets("api_key=sk-abcdef123456")
    assert redact_secrets("project uses Python") == "project uses Python"
    memory = _manager(tmp_path)
    memory.remember_fact("creds", "password: hunter2")
    blob = json.dumps([r.as_dict() for r in memory.store.all()])
    assert "hunter2" not in blob
    assert memory.recall_fact("creds") is not None


# --------------------------------------------------
# embedder gating (production only, never test vectors)
# --------------------------------------------------
def test_embedder_gating(tmp_path):
    from models.embeddings.hash_provider import HashEmbeddingProvider

    memory = _manager(tmp_path)
    assert memory.attach_embedder(HashEmbeddingProvider()) is False
    assert memory.attach_embedder(None) is False

    class Real:
        test_only = False

        def health(self):
            return {"available": True}

        def embed(self, text):
            return [1.0, 0.0]

    assert memory.attach_embedder(Real()) is True
    memory.remember_fact("t", "semantic match material")
    hits = memory.retrieve_relevant("unrelated words entirely")
    assert isinstance(hits, list)  # lexical fallback when no overlap


def test_recent_procedures_history_apis(tmp_path):
    memory = _manager(tmp_path)
    memory.remember_event({"task_id": "t1", "status": "COMPLETED",
                           "metadata": {"goal": "demo goal"}})
    assert memory.recent_events(limit=3)[0]["task_id"] == "t1"
    memory.learn_skill("demo-skill", {"steps": ["a"]})
    assert memory.procedures_for("demo")[0]["skill"] == "demo-skill"
    assert memory.history_snapshot(limit=5) != []
    assert memory.rank_importance(limit=3) != []
    assert memory.reflect()["scanned"] >= 1
    assert memory.forget_unused(before_importance=0.99, limit=100) >= 0


# --------------------------------------------------
# UI / HUD snapshot
# --------------------------------------------------
def test_ui_hud_memory_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from interface.app_controller import HerculeAppController
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    snap = controller.snapshot()
    assert set(snap) >= {"memory"}
    assert snap["memory"]["state"] in ("READY", "RECALLING", "DEGRADED", "UNKNOWN")
    assert controller.memory_snapshot()["storage"] != {}
    services["memory"].retrieve_relevant("test query here")
    assert controller.memory_snapshot()["recall"]["count"] >= 0
    pytest.importorskip("tkinter")
    import tkinter as tk
    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
    except Exception as exc:
        pytest.skip(f"no display available: {exc}")
    from interface.desktop_app import HerculeDesktopApp

    root = tk.Tk()
    root.withdraw()
    try:
        app = HerculeDesktopApp(controller, root=root)
        app._refresh()
        assert "memory" in app.memory_var.get().lower()
        assert app.memory_text_var.get().startswith(("recall:", "recent:"))
    finally:
        root.destroy()
