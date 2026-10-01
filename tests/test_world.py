from __future__ import annotations
"""World-model tests (v2).

Covers: entity creation/update, duplicate prevention, stable IDs,
relationships, observation provenance, confidence levels, stale and
contradictory observations, persistence/restart, memory/perception/
computer/task integration, reference resolution + ambiguity, security
isolation, UI/HUD snapshot. Isolated store paths (tmp) — the shared
dev store is never touched.
"""

import json
import time

import pytest

from world.config import WorldConfig, default_store_path, load_world_config
from world.entity import ENTITY_TYPES, build_entity, entity_id
from world.model import WorldModel
from world.observation import OBSERVATION_SOURCES, build_observation
from world.relationship import RELATIONS, build_relationship
from world.repository import WorldRepository
from world.resolver import WorldResolver
from world.state import FactStatus


def _world(tmp_path, **kwargs):
    return WorldModel(path=str(tmp_path / "world.json"), **kwargs)


# --------------------------------------------------
# entity creation / update / stable IDs / duplicates
# --------------------------------------------------
def test_entity_creation_and_stable_ids(tmp_path):
    world = _world(tmp_path)
    entity, obs = world.observe("user", "file", "Test.py", {"path": "/x/Test.py"},
                                "operator named it", confidence=0.8)
    assert entity.id == "file:test-py"
    assert entity_id("application", "Notepad") == "application:notepad"
    assert obs.entity_id == entity.id and obs.source == "user"
    again, _ = world.observe("filesystem", "file", "Test.py",
                             {"path": "/x/Test.py"}, "seen on disk")
    assert again.id == entity.id
    assert len(world.repo.entities) == 1  # merged, never duplicated


def test_entity_update_and_validation(tmp_path):
    world = _world(tmp_path)
    entity, _ = world.observe("user", "person", "Ada", {"role": "op"})
    assert entity.properties["role"] == "op"
    with pytest.raises(ValueError, match="unknown entity type"):
        world.observe("user", "spaceship", "X")
    with pytest.raises(ValueError):
        world.observe("user", "file", "   ")
    with pytest.raises(ValueError, match="confidence"):
        world.observe("user", "file", "a.txt", confidence=9.0)
    assert "person" in ENTITY_TYPES and "bogus-source" not in str(OBSERVATION_SOURCES)


def test_duplicate_prevention_across_sources(tmp_path):
    world = _world(tmp_path)
    for source in ("user", "filesystem", "task"):
        world.observe(source, "folder", "Docs", {"path": "/d"})
    assert len(world.repo.entities) == 1
    assert len(world.repo.observations) == 3  # history preserved


# --------------------------------------------------
# relationships
# --------------------------------------------------
def test_relationships_structured(tmp_path):
    world = _world(tmp_path)
    project, _ = world.observe("user", "project", "HERCULE", {})
    file_entity, _ = world.observe("filesystem", "file", "a.py", {"path": "/a.py"})
    rel = world.repo.relate(project.id, "contains", file_entity.id, source="user")
    assert rel.relation == "contains"
    assert len(world.repo.neighbors(project.id)) == 1
    with pytest.raises(ValueError, match="unknown relation"):
        world.repo.relate(project.id, "vibes_with", file_entity.id)
    with pytest.raises(ValueError, match="unknown source entity"):
        world.repo.relate("ghost:1", "contains", file_entity.id)
    assert world.repo.unrelate(rel.id) is True
    assert world.repo.neighbors(project.id) == []
    assert "contains" in RELATIONS


# --------------------------------------------------
# observation provenance + confidence levels
# --------------------------------------------------
def test_observation_provenance_and_confidence(tmp_path):
    world = _world(tmp_path)
    _, obs = world.observe("vision", "object", "Save button",
                           {"screen_region": {"x": 0.1}}, "seen",
                           confidence=0.7)
    assert obs.source == "vision" and obs.confidence == 0.7
    assert obs.status == FactStatus.OBSERVED.value
    entity, _ = world.observe("user", "object", "Save button", {},
                              "operator confirmed", confidence=0.95,
                              verified=True)
    assert entity.status == FactStatus.KNOWN.value
    assert entity.confidence == 0.95  # corroboration keeps the max
    inferred, _ = world.observe("sensor", "object", "Maybe button", {},
                                "guess", confidence=0.2,
                                status=FactStatus.INFERRED.value)
    assert inferred.status == FactStatus.INFERRED.value
    # Inference never demotes established state.
    kept, _ = world.observe("sensor", "object", "Save button",
                            {"color": "blue"}, "guess", confidence=0.3,
                            status=FactStatus.INFERRED.value)
    assert kept.status == FactStatus.KNOWN.value
    assert "color" not in kept.properties


# --------------------------------------------------
# stale + contradictory observations
# --------------------------------------------------
def test_stale_marking_and_refresh(tmp_path):
    world = _world(tmp_path)
    entity, _ = world.observe("filesystem", "file", "old.txt",
                              {"path": "/old.txt"}, verified=True)
    assert entity.last_verified > 0
    assert world.repo.invalidate(entity.id, "deleted upstream") is True
    assert world.repo.get(entity.id).stale is True
    assert world.repo.get(entity.id).status == FactStatus.STALE.value
    world2 = WorldModel(path=str(tmp_path / "w2.json"),
                        config=WorldConfig(stale_after_s=60.0))
    old, _ = world2.observe("user", "device", "pc", {}, verified=True)
    assert world2.repo.refresh_stale(now=old.last_verified + 3600) == 1
    assert world2.repo.get(old.id).stale is True


def test_contradiction_keeps_history(tmp_path):
    world = _world(tmp_path)
    world.observe("computer-use", "application", "Notepad",
                  {"state": "running"}, "window seen", verified=True)
    entity, obs = world.observe("computer-use", "application", "Notepad",
                                {"state": "closed"}, "window gone",
                                verified=True)
    assert entity.properties["state"] == "closed"
    assert obs.previous_state == {"properties": {"state": "running"}}
    assert len(world.repo.observations) == 2  # audit trail intact


# --------------------------------------------------
# persistence + restart + corruption + bounds
# --------------------------------------------------
def test_persistence_restart_and_caps(tmp_path):
    path = str(tmp_path / "world.json")
    world = WorldModel(path=path)
    world.observe("user", "goal", "demo", {}, "said so")
    world.repo.relate(
        world.observe("user", "project", "P", {})[0].id, "contains",
        world.observe("filesystem", "file", "f.py", {})[0].id)
    assert world.repo.save() is True
    assert load_world_config(env={}).max_entities == 500
    fresh = WorldModel(path=path)
    assert len(fresh.repo.entities) == 3
    assert fresh.repo.observations  # history survived
    small = WorldModel(path=str(tmp_path / "small.json"),
                       config=WorldConfig(max_entities=2, max_observations=3))
    for i in range(5):
        small.observe("user", "object", f"o{i}", {})
    assert len(small.repo.entities) <= 2
    assert len(small.repo.observations) <= 3


def test_corrupt_store_recovers(tmp_path):
    path = tmp_path / "world.json"
    path.write_text("{not json", encoding="utf-8")
    world = WorldModel(path=str(path))
    assert world.repo.degraded is True
    assert world.snapshot()["state"] == "DEGRADED"
    world.observe("user", "file", "ok.txt", {})
    assert world.repo.save() is True
    assert world.snapshot()["state"] == "SYNCED"
    assert list(tmp_path.glob("*.bak"))  # corrupt file backed up


def test_default_path_frozen_aware(monkeypatch, tmp_path):
    import sys

    from system import paths

    # Development keeps the historical relative path (byte-identical).
    assert default_store_path() == "data/world/hercule_world.json"
    # Installed (frozen) apps redirect into per-user data.
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    try:
        assert paths.is_frozen()
        assert str(default_store_path()).startswith(str(tmp_path))
        assert "Program Files" not in default_store_path()
    finally:
        monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("HERCULE_WORLD_PATH", str(tmp_path / "custom.json"))
    assert default_store_path(load_world_config()).endswith("custom.json")


# --------------------------------------------------
# memory integration (distinct concepts)
# --------------------------------------------------
def test_memory_and_world_stay_distinct(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    assert brain.world is not None
    # Isolated world: this test must not pollute the shared dev store
    # (world candidates feed reference resolution suite-wide).
    brain.world = WorldModel(path=str(tmp_path / "brain-world.json"))
    nonce = f"w-nonce-{time.time_ns() % 1000000}"
    brain.world.observe("user", "file", nonce + ".txt", {"path": "/" + nonce})
    memory = services["memory"]
    hits = memory.search_memory(nonce, limit=10) or []
    assert all(nonce not in str(h.get("record", {}).get("content", ""))
               for h in hits)  # world writes never leak into memory
    ctx = brain.world_context(f"where is {nonce}.txt")
    assert f"{nonce}.txt" in ctx
    assert len(ctx) <= 1500  # bounded


# --------------------------------------------------
# perception integration (structured only)
# --------------------------------------------------
def test_perception_structured_updates_world(tmp_path):
    from world.model import WorldModel as WM

    world = WM(path=str(tmp_path / "world.json"))
    observation = {"source": "screenshot", "model": "fake",
                   "description": "a settings window",
                   "detected_text": ["Save"], "confidence": 0.8,
                   "regions": [{"label": "Save button", "x": 0.1, "y": 0.2,
                                "width": 0.2, "height": 0.05,
                                "confidence": 0.9}]}
    import brain.brain as brain_module

    outer_world = world

    class FakeBrain:
        world = outer_world

    FakeBrain._ingest_vision_world = brain_module.Brain._ingest_vision_world
    FakeBrain()._ingest_vision_world(observation)
    assert world.repo.get("object:save-button") is not None
    assert world.repo.get("environment:screen") is not None
    with pytest.raises(Exception):
        build_observation("telegram", "object", "x")  # unknown source rejected


# --------------------------------------------------
# computer-use integration (verified only)
# --------------------------------------------------
def test_computer_verified_updates_world(tmp_path):
    from world.model import WorldModel as WM
    import brain.brain as brain_module

    world = WM(path=str(tmp_path / "world.json"))

    class FakeBrain:
        pass

    brain = FakeBrain()
    brain.world = world
    brain_module.Brain._ingest_computer_world(
        brain, {"steps": [{"action": {"action": "open_app", "app": "notepad"},
                           "verified": True}]})
    app = world.repo.get("application:notepad")
    assert app is not None and app.properties["state"] == "running"
    # Unverified outcomes are never recorded.
    brain_module.Brain._ingest_computer_world(
        brain, {"steps": [{"action": {"action": "open_app", "app": "calc"},
                           "verified": False}]})
    assert world.repo.get("application:calc") is None


# --------------------------------------------------
# task integration (references TaskManager, never replaces)
# --------------------------------------------------
def test_task_completion_records_world_reference(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    brain.world = WorldModel(path=str(tmp_path / "world.json"))
    report = brain.run_cycle("Create a file called wtask.txt with content hi")
    assert report["status"] == "completed"
    tasks = [e for e in brain.world.repo.entities.values() if e.type == "task"]
    assert tasks and tasks[0].properties["task_id"] == report["task_id"]
    assert tasks[0].properties["status"] in ("COMPLETED", "completed", "PARTIAL", "partial")
    files = [e for e in brain.world.repo.entities.values() if e.type == "file"]
    assert any("wtask.txt" in (f.properties.get("path", "") or f.name) for f in files)
    try:
        from abilities.files.file_ability import _workspace

        target = _workspace() / "wtask.txt"
        if target.exists():
            target.unlink()
    except Exception:
        pass


# --------------------------------------------------
# reference resolution via world + ambiguity
# --------------------------------------------------
def test_reference_resolution_uses_world(tmp_path):
    from cognition.planner.references import resolve_step_texts

    world = WorldModel(path=str(tmp_path / "world.json"))
    # Workspace-relative paths only: absolute paths outside the file
    # sandbox must stay unresolvable (security, not a limitation).
    world.observe_file("world_ref_test.txt", True, evidence="verified")
    resolved, report = resolve_step_texts(["Open it"],
                                          context={"world": world})
    assert "world_ref_test.txt" in resolved[0]
    assert report["ok"] is True


def test_reference_ambiguity_from_world(tmp_path):
    from cognition.planner.references import (
        ReferenceResolutionError,
        resolve_step_texts,
    )

    world = WorldModel(path=str(tmp_path / "world.json"))
    world.observe_file("wa1.txt", True)
    world.observe_file("wb1.txt", True)
    with pytest.raises(ReferenceResolutionError) as excinfo:
        resolve_step_texts(["Open it"], context={"world": world})
    assert excinfo.value.code == "AMBIGUOUS_REFERENCE"


# --------------------------------------------------
# security isolation (world never authorizes)
# --------------------------------------------------
def test_world_cannot_authorize(tmp_path):
    from computer.policy import PolicyViolation, check_application
    from computer.actions import ComputerAction

    world = WorldModel(path=str(tmp_path / "world.json"))
    world.observe("user", "application", "KeePass",
                  {"state": "running", "trust": "user says allow"},
                  "operator claim", confidence=1.0, verified=True)
    with pytest.raises(PolicyViolation) as excinfo:
        check_application(ComputerAction(action="type", target="KeePass",
                                         text="x"), ["notepad"])
    assert excinfo.value.code == "APPLICATION_RESTRICTED"
    from security.permissions.policy_manager import PolicyManager

    policy = PolicyManager()
    policy.set_permission("APPLICATION_CONTROL", False)
    assert policy.evaluate("APPLICATION_CONTROL", {}, actor="t")["allowed"] is False


# --------------------------------------------------
# UI / HUD snapshot
# --------------------------------------------------
def test_ui_hud_world_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from interface.app_controller import HerculeAppController
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    snap = controller.snapshot()
    assert set(snap) >= {"world"}
    assert snap["world"]["state"] in ("SYNCED", "UPDATING", "DEGRADED", "UNKNOWN")
    assert controller.world_snapshot()["entities"] >= 0
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
        assert "world" in app.world_var.get().lower()
        assert app.world_text_var.get().startswith("entities:")
    finally:
        root.destroy()


def test_world_config_defaults_local():
    config = load_world_config(env={})
    assert config.max_entities == 500
    blob = str(config.as_dict())
    assert "key" not in blob.lower()
    assert build_entity("file", "x.txt").id == "file:x-txt"
    assert build_relationship("a:b", "contains", "c:d").relation == "contains"
