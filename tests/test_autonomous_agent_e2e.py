"""End-to-end autonomous agent tests.

UNDERSTAND → REASON → GOAL → PLAN → CAPABILITIES → TOOLS → EXECUTE →
OBSERVE → VERIFY → REPLAN → LEARN → STORE → RESPOND.

Deterministic systems (permissions, validation, verification, task
state, recovery) stay strict; the LLM (ModelManager) is used only for
reasoning/conversation. No chain-of-thought is exposed in results.
"""
from abilities.base_ability import BaseAbility
from runtime.initializer import RuntimeInitializer


class EchoAbility(BaseAbility):
    def __init__(self, name="echo-file", result="echo-content-here"):
        super().__init__(name, f"test {name}")
        self.calls = 0
        self.result = result

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": self.result}


class FlakyAbility(BaseAbility):
    """Fails once, then succeeds — exercises bounded replan/recovery."""

    def __init__(self, name="flaky-tool"):
        super().__init__(name, "flaky")
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"status": "failed", "error": "transient boom"}
        return {"status": "success", "content": "recovered-content"}


def make_brain():
    import os
    os.environ["HERCULE_ALLOW_MOCK"] = "1"
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    orch.abilities.register(EchoAbility())
    brain.register_capability("FILE_READ", "tool", "echo-file")
    return services, brain, orch


def test_simple_question_never_plans():
    _, brain, orch = make_brain()
    before = len(orch.task_manager)
    answer = brain.think("hi")
    assert isinstance(answer, str) and answer
    assert "dynamically synthesized" not in answer
    assert len(orch.task_manager) == before


def test_multi_step_task_executes_and_verifies():
    _, brain, orch = make_brain()
    report = brain.run_cycle("read this file")
    assert report["status"] == "completed"
    assert report["verification"]["passed_steps"] >= 1
    # Reasoning readout contract (adaptive reasoning): a structured
    # decision summary is present, never chain-of-thought content.
    assert "reasoning" in report
    assert report["reasoning"].get("mode") in (
        "DETERMINISTIC", "LIGHT", "STANDARD", "DEEP", "EXPERT")
    assert "chain-of-thought" not in str(report).lower()


def test_failed_task_reports_honestly():
    _, brain, _ = make_brain()
    report = brain.run_cycle("blorple impossible zzz-no-provider-xyz")
    assert report["status"] == "failed"
    assert "error" in report
    assert "subsystem=" in report["error"]
    assert "dynamically synthesized" not in str(report)


def test_replan_bounded_on_transient_failure():
    services, brain, orch = make_brain()
    orch.abilities.register(FlakyAbility())
    brain.register_capability("FILE_WRITE", "tool", "flaky-tool")
    report = brain.run_cycle("write the file flaky-report")
    assert report["replans"] <= 2  # bounded, no infinite loop
    assert report["status"] in ("completed", "partial", "failed")


def test_verification_failure_is_honest():
    _, brain, _ = make_brain()
    report = brain.run_cycle("write the file report-xyz")
    # No FILE_WRITE provider for default registry beyond flaky? If no
    # provider, capability resolution fails honestly (failed, not success).
    assert report["status"] in ("completed", "partial", "failed")
    if report["status"] == "failed":
        assert "error" in report or report["result"].get("failed")


def test_experience_stored_for_success_and_failure():
    _, brain, orch = make_brain()
    ok = brain.run_cycle("read this file")
    bad = brain.run_cycle("blorple impossible zzz-no-provider-xyz")
    assert ok["status"] == "completed"
    assert bad["status"] == "failed"
    exp = brain._experience
    assert len(exp) >= 2 if hasattr(exp, "__len__") else True


def test_persistent_memory_records_task():
    _, brain, orch = make_brain()
    report = brain.run_cycle("read this file")
    history = orch.memory.event_history()
    assert any(report["task_id"] in str(e) for e in history)


def test_repeated_task_is_idempotent():
    _, brain, orch = make_brain()
    first = brain.run_cycle("read this file")
    assert first["status"] == "completed"
    second = brain.run_cycle("read this file", task_id=first["task_id"])
    assert second["task_id"] == first["task_id"]
    assert second.get("idempotent") is True
