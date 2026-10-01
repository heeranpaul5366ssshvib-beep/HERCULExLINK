"""Conversation vs autonomous task separation + honest healing.

Covers: greeting, identity, general question, valid task, invalid task,
missing capability, failed verification, self-healing activation scope,
conversation NOT triggering healing, consciousness transitions.
"""
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


class FailingAbility(BaseAbility):
    def __init__(self, name="fail-tool"):
        super().__init__(name, "always fails")

    def execute(self, *args, **kwargs):
        return {"status": "failed", "error": "boom"}


@pytest.fixture()
def harness():
    boot = load_boot_module()
    services = boot.initialize_runtime()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.register(EchoAbility())
    brain.register_capability("FILE_READ", "tool", "echo-file")
    return boot, services, brain, orch, boot.HerculeCli(brain)


def test_greeting_is_question_not_task(harness):
    boot, services, brain, orch, cli = harness
    assert boot.classify_request("hi") == "QUESTION"
    assert boot.classify_request("hello") == "QUESTION"
    before = len(orch.task_manager)
    result = cli.handle_line("hi")
    assert result["kind"] == "QUESTION" and result["status"] == "answered"
    assert len(orch.task_manager) == before
    assert "dynamically synthesized" not in str(result.get("response", ""))


def test_identity_question_is_conversation(harness):
    boot, services, brain, orch, cli = harness
    assert boot.classify_request("what is your name") == "QUESTION"
    assert boot.classify_request("who are you") == "QUESTION"
    result = cli.handle_line("what is your name")
    assert result["kind"] == "QUESTION"
    assert "dynamically synthesized" not in str(result.get("response", ""))


def test_general_question_is_conversation(harness):
    boot, services, brain, orch, cli = harness
    result = cli.handle_line("explain gravity briefly")
    assert result["kind"] == "QUESTION"


def test_valid_task_uses_autonomous_path(harness):
    boot, services, brain, orch, cli = harness
    assert boot.classify_request("calculate 25 * 4") in ("GOAL", "COMMAND")
    result = cli.handle_line("calculate 25 * 4")
    assert result["kind"] in ("GOAL", "COMMAND")
    assert result["status"] in ("completed", "partial", "failed")
    assert "task_id" in result and "correlation_id" in result


def test_invalid_task_reports_honest_failure(harness):
    boot, services, brain, orch, cli = harness
    result = cli.handle_line("blorple the zindlewop")
    # No capabilities and no family -> conversation, or honest task failure.
    assert result["kind"] in ("QUESTION", "GOAL", "COMMAND")
    if result["kind"] != "QUESTION":
        assert result["status"] == "failed"
        assert "dynamically synthesized" not in str(result)


def test_missing_capability_is_structured(harness):
    _, _, brain, _, _ = harness
    problems = brain._plan_contract_problems([{
        "step_id": "step-1", "goal": "do the impossible",
        "required_capabilities": [], "verification_criteria": [],
    }])
    assert any("MISSING_CAPABILITIES" in p for p in problems)
    assert any("MISSING_VERIFICATION" in p for p in problems)


def test_planner_contract_enforced(harness):
    _, _, brain, _, _ = harness
    good = [{"step_id": "step-1", "goal": "read file",
             "required_capabilities": ["FILE_READ"],
             "verification_criteria": ["content returned"]}]
    assert brain._plan_contract_problems(good) == []


def test_failed_verification_path(harness):
    boot, services, brain, orch, cli = harness
    orch.abilities.register(FailingAbility())
    brain.register_capability("FILE_WRITE", "tool", "fail-tool")
    # Isolate the failing provider: the real sandboxed files ability would
    # otherwise satisfy FILE_WRITE honestly (defaults materialize inside
    # run_cycle, so ensure them before disabling).
    orch.abilities.ensure_defaults()
    orch.abilities.disable("files")
    try:
        result = brain.run_cycle("write the file report-xyz")
    finally:
        orch.abilities.enable("files")
    assert result["status"] in ("failed", "partial")
    assert "task_id" in result


def test_self_healing_only_on_genuine_failure(harness):
    from system.guardian_patch import UniversalFallbackMixin

    class Dummy(UniversalFallbackMixin):
        pass

    with pytest.raises(AttributeError) as excinfo:
        Dummy().nonexistent_method()
    assert "dynamically synthesized" not in str(excinfo.value)
    assert "subsystem='Dummy'" in str(excinfo.value)


def test_conversation_does_not_trigger_healing(harness):
    boot, services, brain, orch, cli = harness
    result = cli.handle_line("hi")
    assert result["kind"] == "QUESTION"
    assert "Autonomous Recovery" not in str(result.get("response", ""))
    assert "dynamically synthesized" not in str(result.get("response", ""))


def test_consciousness_transitions_conversation(harness):
    _, _, brain, _, _ = harness
    brain.consciousness.set_state("ACTIVE", "test")
    brain.think("hi")
    states = [h["state"] for h in brain.consciousness.state_history]
    assert "THINKING" in states
    assert brain.consciousness.get_state() in ("ACTIVE", "IDLE")


def test_consciousness_transitions_task(harness):
    _, _, brain, _, _ = harness
    brain.consciousness.set_state("ACTIVE", "test")
    brain.run_cycle("calculate 2 + 2")
    states = [h["state"] for h in brain.consciousness.state_history]
    assert "PLANNING" in states
    assert "EXECUTING" in states or "ERROR" in states


def test_consciousness_transitions_failure_and_shutdown(harness):
    _, _, brain, _, _ = harness
    brain.consciousness.set_state("ACTIVE", "test")
    brain.run_cycle("blorple impossible capability zzz-no-provider")
    states = [h["state"] for h in brain.consciousness.state_history]
    assert "PLANNING" in states
    brain.stop()
    assert brain.consciousness.get_state() == "IDLE"
    brain.start()
    assert brain.consciousness.get_state() == "ACTIVE"


def test_health_exposes_no_chain_of_thought(harness):
    _, _, brain, _, _ = harness
    health = brain.health()
    assert "state" in health and "recent_states" in health
    assert "reasoning" not in health
    blob = str(health)
    assert "chain-of-thought" not in blob


def test_slash_health_reports_live_status_without_tasks(harness):
    boot, _, _, _, cli = harness
    result = cli.handle_line("/health")
    assert result["kind"] == "STATUS"
    assert result["status"] == "ok"
    text = boot.HerculeCli.format_response(result)
    for section in ("runtime", "brain", "models", "memory", "tasks",
                    "autonomy", "abilities", "security"):
        assert section in text
    # No task lifecycle may start from a diagnostics command.
    assert cli.brain.goals.active_goals() == []


def test_slash_status_alias_and_no_model_calls(harness):
    boot, _, brain, _, cli = harness
    calls = []
    manager = brain.orchestrator.models
    real_generate = manager.generate if hasattr(manager, "generate") else None
    if real_generate is not None:
        def spy(*args, **kwargs):
            calls.append(args)
            return real_generate(*args, **kwargs)
        manager.generate = spy
    try:
        result = cli.handle_line("/status")
        assert result["kind"] == "STATUS"
    finally:
        if real_generate is not None:
            manager.generate = real_generate
    assert calls == []
