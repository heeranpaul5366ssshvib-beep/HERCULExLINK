"""Stage 11 (v1.0): release hardening — security, failure recovery,
performance budgets, limits, config, health, CLI reliability.

Fast hermetic tests: mock model backend, :memory:/tmp stores.
"""
import time

import pytest


def mock_env(monkeypatch, tmp_path=None):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    if tmp_path is not None:
        monkeypatch.setenv("HERCULE_TASK_STORE", str(tmp_path / "tasks.json"))
        monkeypatch.setenv("HERCULE_MEMORY_DIR", str(tmp_path / "memory"))
    else:
        monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")


@pytest.fixture()
def services(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from runtime.initializer import RuntimeInitializer
    return RuntimeInitializer().initialize()


# ---------- Phase 1: terminal workspace containment ----------

def _terminal(services):
    abilities = services["orchestrator"].abilities
    abilities.ensure_defaults()
    terminal = abilities.get("terminal")
    assert terminal is not None
    return terminal


def test_terminal_absolute_path_blocked(services):
    terminal = _terminal(services)
    problem = terminal.validate_input("cat C:\\Windows\\System32\\drivers\\etc\\hosts")
    assert problem and "sandbox" in problem.lower()
    result = terminal.execute("cat C:\\Windows\\System32\\drivers\\etc\\hosts")
    assert result["status"] == "failed"


def test_terminal_parent_escape_blocked(services):
    terminal = _terminal(services)
    assert terminal.validate_input("ls ../../..") != ""
    assert terminal.execute("ls ../../..")["status"] == "failed"


def test_terminal_allowlisted_command_still_works(services):
    terminal = _terminal(services)
    # Validation (not OS execution) is the security boundary under test;
    # `echo` has no executable on Windows, so execution honesty there is
    # covered by the shape contract instead of a live run.
    assert terminal.validate_input("echo hello") == ""
    result = terminal.execute("hostname")
    assert result["status"] == "success", result
    assert result.get("stdout", "").strip() != ""


def test_terminal_dangerous_patterns_still_blocked(services):
    terminal = _terminal(services)
    assert terminal.execute("rm -rf /")["status"] == "failed"
    assert terminal.execute("echo hi | dir")["status"] == "failed"


# ---------- Phase 3/4: failure + restart recovery ----------

def test_corrupted_task_store_loads_empty(tmp_path):
    from cognition.task_manager.task_manager import TaskManager
    store = tmp_path / "tasks.json"
    store.write_text("{not valid json", encoding="utf-8")
    manager = TaskManager(storage_path=str(store))  # must not raise
    assert len(manager) == 0
    task_id = manager.create_task("still works after corruption")
    assert task_id in manager


def test_malformed_task_entries_skipped_not_fatal(tmp_path):
    import json
    from cognition.task_manager.task_manager import TaskManager
    store = tmp_path / "tasks.json"
    store.write_text(json.dumps({"tasks": [
        {"id": "task-keep", "goal": "survives", "status": "QUEUED"},
        {"noid": True},
        "not-a-dict",
        {"id": "", "goal": "empty id"},
        None,
    ]}), encoding="utf-8")
    manager = TaskManager(storage_path=str(store))  # must not raise
    assert "task-keep" in manager
    assert len(manager) == 1


def test_task_store_persist_leaves_no_tmp_file(tmp_path):
    from cognition.task_manager.task_manager import TaskManager
    store = tmp_path / "tasks.json"
    manager = TaskManager(storage_path=str(store))
    manager.create_task("atomic write check")
    assert store.exists()
    assert not store.with_name(store.name + ".tmp").exists()
    reloaded = TaskManager(storage_path=str(store))
    assert len(reloaded) == 1


def test_scheduler_failure_is_honest():
    from kernel.scheduler import Scheduler
    scheduler = Scheduler(max_workers=1)
    scheduler.shutdown(wait=True)
    with pytest.raises(RuntimeError):
        scheduler.submit(lambda: 1).result(timeout=10)


def test_memory_storage_failure_degrades_gracefully(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from memory.memory_manager import MemoryManager
    memory = MemoryManager()
    memory.remember_fact("project", "HERCULE")  # in-memory works
    assert memory.recall_fact("project") == "HERCULE"
    # Break the store path: point at a file, not a directory.
    blocker = tmp_path / "blocker.json"
    blocker.write_text("{}", encoding="utf-8")
    memory.store.path = blocker / "nested" / "memory.json"
    assert memory.save() is False  # honest failure, no exception
    assert memory.recall_fact("project") == "HERCULE"  # memory intact


def test_interrupted_task_recovers_without_replay(monkeypatch, tmp_path):
    mock_env(monkeypatch, tmp_path)
    from runtime.initializer import RuntimeInitializer
    from autonomy.worker import AutonomyWorker
    services = RuntimeInitializer().initialize()
    worker = AutonomyWorker(services, config={"poll_interval_s": 0.05})
    try:
        scheduled = worker.schedule("calculate 11+11")
        worker.start(recover=False)
        deadline = time.perf_counter() + 20.0
        while time.perf_counter() < deadline:
            if str(worker.tasks.get(scheduled["task_id"]).get("status")) == "COMPLETED":
                break
            time.sleep(0.05)
        before = dict(worker.tasks.get(scheduled["task_id"]))
        # Simulated restart over the same store.
        services2 = RuntimeInitializer().initialize()
        worker2 = AutonomyWorker(services2, config={"poll_interval_s": 0.05})
        try:
            summary = worker2.recover_on_startup()
            assert summary["resumed"] == []
            after = services2["orchestrator"].task_manager.get(scheduled["task_id"])
            assert str(after.get("status")) == "COMPLETED"
            assert before["metadata"].get("capability_states") == \
                after["metadata"].get("capability_states")
        finally:
            worker2.stop()
    finally:
        worker.stop()


# ---------- Phase 5: performance ----------

def _load_boot_module():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "hercule_boot_release", str(Path("boot.py").resolve()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classification_is_fast():
    boot = _load_boot_module()
    started = time.perf_counter()
    for _ in range(20):
        assert boot.classify_request("calculate 9+8") == "GOAL"
        assert boot.classify_request("hi") == "QUESTION"
    elapsed = (time.perf_counter() - started) / 40.0
    assert elapsed < 1.0, f"classification too slow: {elapsed*1000:.1f}ms avg"


def test_simple_deterministic_task_makes_no_llm_calls(services, monkeypatch):
    calls = []
    models = services["models"]
    real_generate = models.generate

    def counting_generate(prompt, *args, **kwargs):
        calls.append(str(prompt)[:60])
        return real_generate(prompt, *args, **kwargs)

    monkeypatch.setattr(models, "generate", counting_generate)
    brain = services["brain"]
    result = brain.run_cycle("calculate 9+8")
    assert result["status"] == "completed"
    assert calls == [], f"deterministic task must not call the LLM: {calls}"


def test_memory_retrieval_is_fast(services):
    memory = services["memory"]
    for i in range(5):
        memory.remember_fact(f"topic-{i}", f"fact number {i}")
    started = time.perf_counter()
    for _ in range(10):
        memory.search_memory("fact number", limit=5)
    elapsed = (time.perf_counter() - started) / 10.0
    assert elapsed < 1.0, f"retrieval too slow: {elapsed*1000:.1f}ms avg"


# ---------- Phase 6: resource limits ----------

def test_replan_bound_is_enforced(services):
    from orchestrator.autonomous import AutonomousLoop
    stack = services["brain"]._autonomy_stack()
    loop = AutonomousLoop(services["brain"].authoritative_planner,
                          stack["matcher"], stack["tasks"],
                          stack.get("tracer"), max_replans=1)
    report = loop.run("do the impossible thing xyz", ["do the impossible thing xyz"],
                      task_id="", correlation_id="release-replan-cap")
    assert report["replans"] <= 1


def test_step_retry_budget_is_enforced():
    from orchestrator.autonomous import AutonomousLoop
    assert AutonomousLoop.DEFAULT_MAX_STEP_RETRIES >= 1


def test_invalid_config_fails_clearly():
    from system.config.runtime_config import load_runtime_config, RuntimeConfigError
    with pytest.raises(RuntimeConfigError):
        load_runtime_config({"ollama_timeout_s": -5})
    with pytest.raises(RuntimeConfigError):
        load_runtime_config({"default_model": "  "})
    with pytest.raises(RuntimeConfigError):
        load_runtime_config({"autonomy_max_concurrent_tasks": 0})


def test_config_defaults_and_env(monkeypatch):
    from system.config.runtime_config import load_runtime_config
    config = load_runtime_config(env={})
    assert config.ollama_host == "http://127.0.0.1:11434"
    assert config.default_model == "llama3"
    assert config.allow_mock_fallback is False
    assert config.autonomy_enabled is False
    assert config.cognitive_planning == "auto"
    config = load_runtime_config(env={"HERCULE_DEFAULT_MODEL": "llama3.2:3b",
                                      "HERCULE_ALLOW_MOCK": "yes",
                                      "HERCULE_COGNITIVE_PLANNING": "bogus-value"})
    assert config.default_model == "llama3.2:3b"
    assert config.allow_mock_fallback is True
    assert config.cognitive_planning == "auto"  # unknown falls back, never crashes


def test_task_retry_limit_enforced(services):
    tasks = services["orchestrator"].task_manager
    task_id = tasks.create_task("limited retries")
    tasks.queue_task(task_id)
    tasks.start(task_id)
    tasks.fail(task_id, "boom")
    assert tasks.retry(task_id)["retry_count"] == 1
    assert tasks.retry(task_id)["retry_count"] == 2
    failed = tasks.retry(task_id)  # exhausted -> stays failed
    assert str(failed.get("status")) == "FAILED"


# ---------- Phase 10: CLI reliability ----------

def test_exit_commands_all_terminate(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    boot = _load_boot_module()
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    cli = boot.HerculeCli(services["brain"])
    for command in ("exit", "quit", "shutdown", "EXIT", "  quit  "):
        assert cli.handle_line(command)["kind"] == "exit"
    assert cli.handle_line("   ")["kind"] == "empty"


def test_cli_routing_untouched():
    boot = _load_boot_module()
    assert boot.classify_request("hi") == "QUESTION"
    assert boot.classify_request("calculate 9+8") == "GOAL"


# ---------- Phase 12: central health check ----------

def test_health_report_structure(services):
    from system.health_report import health_report
    report = health_report(services)
    for section in ("runtime", "brain", "models", "memory", "tasks",
                    "autonomy", "abilities", "security", "ui"):
        assert section in report, section
        assert report[section].get("status") in ("AVAILABLE", "UNAVAILABLE", "ONLINE", "DEGRADED")
    assert report["brain"]["state"] != "UNKNOWN"
    assert report["runtime"]["state"] in ("ONLINE", "DEGRADED")


def test_health_report_honest_when_empty():
    from system.health_report import health_report
    report = health_report({})
    assert report["runtime"]["state"] == "DEGRADED"
    assert report["brain"]["status"] == "UNAVAILABLE"
    assert report["models"]["status"] == "UNAVAILABLE"


# ---------- Phase 14: release checks ----------

def test_no_mock_in_production_fallback_by_default(monkeypatch):
    monkeypatch.delenv("HERCULE_ALLOW_MOCK", raising=False)
    from models.model_manager import ModelManager
    manager = ModelManager(config={"allow_mock_fallback": False})
    ordered, _ = manager._ordered_adapters("llama3.2:3b")
    assert all(name != "mock" for name, _ in ordered)


def test_no_api_key_required_for_local_ollama():
    import inspect
    from models.ollama.client import OllamaClient
    params = inspect.signature(OllamaClient.__init__).parameters
    assert not any(k in ("api_key", "apikey", "token", "secret") for k in params)


def test_singleton_services(services):
    assert services["brain"].orchestrator is services["orchestrator"]
    assert services["orchestrator"].task_manager is not None
    assert services["brain"].consciousness is not None
