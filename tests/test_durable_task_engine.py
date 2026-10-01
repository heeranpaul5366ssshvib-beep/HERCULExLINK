import json
import os

import pytest

from cognition.task_manager.task_manager import TaskManager
from orchestrator.orchestrator import Orchestrator
from security.permissions.policy_manager import PolicyManager


class DummyServices:
    def __init__(self):
        self.memory = type("Memory", (), {"health": lambda self: {"ok": True}})()
        self.knowledge = type("Knowledge", (), {"health": lambda self: {"ok": True}})()
        self.models = type("Models", (), {"health": lambda self: {"ok": True}})()
        self.abilities = type("Abilities", (), {"health": lambda self: {"ok": True}})()
        self.perception = type("Perception", (), {"health": lambda self: {"ok": True}})()
        self.communication = type("Communication", (), {"health": lambda self: {"ok": True}})()
        self.security = type("Security", (), {"health": lambda self: {"ok": True}})()
        self.system = type("System", (), {"status": lambda self: {"healthy": True}})()


def test_task_state_machine_validates_transitions():
    manager = TaskManager()
    task_id = manager.create_task("Build report", timeout=30)

    manager.queue_task(task_id)
    manager.start(task_id)
    manager.pause(task_id)
    manager.resume(task_id)

    with pytest.raises(ValueError):
        manager.transition(task_id, "COMPLETED")

    assert manager.get(task_id)["status"] == "RUNNING"


def test_task_persistence_and_recovery_after_restart():
    path = "./tmp_task_store.json"
    if os.path.exists(path):
        os.remove(path)

    manager = TaskManager(storage_path=path)
    task_id = manager.create_task("Investigate model failures", timeout=45)
    manager.queue_task(task_id)
    manager.start(task_id)
    manager.record_checkpoint(task_id, {"step": 1, "status": "running"})

    restored = TaskManager(storage_path=path)
    assert restored.get(task_id)["status"] in {"RUNNING", "QUEUED"}
    assert restored.get(task_id)["checkpoints"]

    os.remove(path)


def test_pause_resume_revalidates_permissions_before_resumption():
    policy = PolicyManager()
    policy.set_permission("FILE_WRITE", False)
    manager = TaskManager(policy=policy)
    task_id = manager.create_task(
        "Write incident summary",
        timeout=30,
        required_permissions=["FILE_WRITE"],
    )
    manager.queue_task(task_id)
    manager.start(task_id)
    manager.pause(task_id)

    with pytest.raises(RuntimeError):
        manager.resume(task_id)

    assert manager.get(task_id)["status"] == "PAUSED"


def test_cancellation_and_verification_require_criteria():
    manager = TaskManager()
    task_id = manager.create_task("Verify router behavior", timeout=10)
    manager.queue_task(task_id)
    manager.start(task_id)

    assert manager.cancel(task_id)["status"] == "CANCELLED"

    task_id_2 = manager.create_task("Deploy patch", timeout=15, expected_result={"status": "ok"})
    manager.queue_task(task_id_2)
    manager.start(task_id_2)
    with pytest.raises(ValueError):
        manager.complete(task_id_2, result={"status": "bad"})


def test_durable_queue_and_dependency_checks():
    manager = TaskManager()
    parent = manager.create_task("Root task", timeout=20)
    child = manager.create_task("Dependent task", timeout=20, dependencies=[parent])

    manager.queue_task(parent)
    manager.queue_task(child)
    assert manager.get(child)["status"] == "WAITING"

    manager.start(parent)
    manager.complete(parent, result={"status": "ok"}, validation={"verified": True})
    manager.start(child)

    assert manager.get(child)["status"] == "RUNNING"
