"""Phase L-A: CLI -> Brain.run_cycle canonical boot path."""

import importlib.util
from pathlib import Path

import pytest

from abilities.base_ability import BaseAbility
from runtime.initializer import RuntimeInitializer


def load_boot_module():
    spec = importlib.util.spec_from_file_location("hercule_boot", str(Path("boot.py").resolve()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EchoAbility(BaseAbility):
    def __init__(self, name="echo-file", result="echo-content-here"):
        super().__init__(name, f"test {name}")
        self.calls = 0
        self.result = result

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": self.result}


@pytest.fixture()
def cli():
    boot = load_boot_module()
    services = boot.initialize_runtime()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.register(EchoAbility())
    brain.register_capability("FILE_READ", "tool", "echo-file")
    return boot, services, brain, orch


def test_boot_initializes_canonical_runtime(cli):
    boot, services, brain, orch = cli
    for key in ("brain", "orchestrator", "memory", "knowledge", "models"):
        assert key in services, key
    assert brain.orchestrator is orch
    assert hasattr(services["orchestrator"], "task_manager")


def test_classify_request_splits_question_and_goal(cli):
    boot, _, _, _ = cli
    assert boot.classify_request("hello there friend") == "QUESTION"
    assert boot.classify_request("Calculate 2+2") == "GOAL"
    assert boot.classify_request("/run the tests now") == "COMMAND"
    assert boot.classify_request("Research this topic") == "GOAL"
    assert boot.EXIT_COMMANDS == ("exit", "quit", "shutdown")


def test_empty_and_exit_lines(cli):
    boot, _, brain, _ = cli
    harness = boot.HerculeCli(brain)
    assert harness.handle_line("   ")["kind"] == "empty"
    assert harness.handle_line("quit")["kind"] == "exit"
    assert "Shutting" in harness.format_response({"kind": "exit"})
    assert harness.format_response({"kind": "empty"}) == ""


def test_goal_reaches_brain_run_cycle_not_model_generate(cli):
    boot, services, brain, orch = cli
    harness = boot.HerculeCli(brain)
    models = services["models"]
    real_generate = models.generate
    models.generate = lambda *a, **k: "MODEL-SENTINEL-DIRECT"
    try:
        result = harness.handle_line("Read this file")
    finally:
        models.generate = real_generate
    assert result["status"] == "completed"  # task path, not model text
    assert result["kind"] == "GOAL"
    assert str(tasks_of(orch, result)) == "COMPLETED"
    rendered = harness.format_response(result)
    assert "MODEL-SENTINEL-DIRECT" not in rendered  # response derives from tools
    assert "echo-content-here" in rendered or "COMPLETED" in rendered


def tasks_of(orch, result):
    return orch.task_manager.get(result["task_id"])["status"]


def test_question_path_does_not_create_tasks(cli):
    boot, _, brain, orch = cli
    harness = boot.HerculeCli(brain)
    before = len(orch.task_manager)
    result = harness.handle_line("hello there friend")
    assert result["kind"] == "QUESTION" and result["status"] == "answered"
    assert len(orch.task_manager) == before  # conversational: no task lifecycle
    assert harness.format_response(result) != ""


def test_cli_policy_verification_tracing(cli):
    boot, services, brain, orch = cli
    harness = boot.HerculeCli(brain)
    orch.abilities.policy.set_permission("FILE_READ", False)
    try:
        denied = harness.handle_line("Read this file")
    finally:
        orch.abilities.policy.set_permission("FILE_READ", True)
    assert denied["status"] == "failed"
    assert orch.abilities.get("echo-file").calls == 0
    assert "FAILED" in harness.format_response(denied)
    ok = harness.handle_line("Read this file")
    assert ok["status"] == "completed"
    assert ok["verification"]["passed_steps"] >= 1
    trace = brain._tracer.get(ok["correlation_id"]).as_dict()["stages"]
    for stage in ("request", "task_creation", "plan_validation", "execution", "verification", "completion"):
        assert stage in trace, stage


def test_cli_failures_are_structured(cli):
    boot, _, brain, orch = cli
    harness = boot.HerculeCli(brain)
    orch.abilities.policy.set_permission("FILE_READ", False)
    try:
        result = harness.handle_line("Read this file")
    finally:
        orch.abilities.policy.set_permission("FILE_READ", True)
    assert result["status"] == "failed"
    assert "task_id" in result and "correlation_id" in result
    assert "reasoning" not in result
    assert result["kind"] == "GOAL"
    assert "FAILED" in harness.format_response(result)
