from __future__ import annotations
"""Adaptive reasoning controller tests (v2 Phase 4).

Covers: deterministic fast path, light/standard/deep/expert routing,
complexity + risk classification, model unavailable, provider
switching, budget enforcement, timeout, multi-pass limits,
world-model shortcut, memory-aware context, experience
promotion/demotion bounds, conversation isolation, security
isolation, Brain decision shape, UI/HUD snapshot. A stub model
inventory keeps routing tests hermetic (no servers, no weights).
"""

import time

import pytest

from cognition.reasoning.controller import (
    MODES,
    AdaptiveReasoningController,
    assess_complexity,
    assess_risk,
    select_mode,
)


class StubModels:
    """Hermetic ModelManager stand-in with a fixed inventory."""

    def __init__(self, models=None, default="mid-1b", calls=None):
        self._models = list(models if models is not None else [
            {"id": "tiny-100m", "provider": "builtin", "size": 100,
             "thinking": False, "context": 2048, "capabilities": ["chat"]},
            {"id": "mid-1b", "provider": "builtin", "size": 1000,
             "thinking": False, "context": 4096, "capabilities": ["chat"]},
            {"id": "big-8b", "provider": "ollama", "size": 8000,
             "thinking": True, "context": 8192, "capabilities": ["chat"]},
        ])
        self.default_model = default
        self.provider_pref = "auto"
        self.calls = calls if calls is not None else []

    def inventory_for_controller(self):
        return self._models

    def generate(self, prompt, model=None, timeout_s=None, **kwargs):
        self.calls.append({"prompt": prompt, "model": model,
                           "timeout_s": timeout_s, "kwargs": kwargs})
        if timeout_s is not None and timeout_s <= 0:
            raise TimeoutError("budget exhausted")
        return f"answer[{model}]"


class ControllerStub(AdaptiveReasoningController):
    def inventory(self):
        return list(self.models.inventory_for_controller())


def _controller(**kwargs):
    return ControllerStub(StubModels(**kwargs))


# --------------------------------------------------
# fast path + mode routing
# --------------------------------------------------
def test_deterministic_fast_path():
    decision = _controller().decide("calculate 25 * 4")
    assert decision["mode"] == "DETERMINISTIC"
    assert decision["budget"]["max_tokens"] == 0
    assert decision["risk"] == "LOW"


def test_light_routing():
    decision = _controller().decide("what is your name?", is_question=True)
    assert decision["mode"] == "LIGHT"
    assert decision["model"] == "tiny-100m"  # smallest installed
    assert decision["budget"]["max_tokens"] == 64


def test_standard_routing():
    decision = _controller().decide(
        "Explain how the current HERCULE architecture works.")
    assert decision["mode"] == "STANDARD"
    assert decision["model"] == "mid-1b"  # configured default


def test_deep_routing():
    decision = _controller().decide(
        "Create a file, write content, read it back, verify it.")
    assert decision["mode"] == "DEEP"
    assert decision["risk"] == "HIGH"  # risk tracked separately


def test_expert_routing_needs_extreme_complexity():
    hard = ("Design, implement, debug, refactor, and verify a distributed "
            "cache with failover, sharding, replication, monitoring, "
            "alerting, backups, multi-region synchronization, zero-downtime "
            "migration, rollback planning, load testing, chaos testing, "
            "capacity planning, cost analysis, and compliance review, then "
            "document it all with runbooks and diagrams for twelve services.")
    decision = _controller().decide(
        hard, context={"recent_failures": 3})
    assert decision["mode"] == "EXPERT"
    assert decision["model"] == "big-8b"  # thinking-capable
    assert decision["budget"]["max_passes"] == 4


# --------------------------------------------------
# complexity + risk classification
# --------------------------------------------------
def test_complexity_signals_deterministic():
    first = assess_complexity("Create a, then b, then verify it", ["FILE_WRITE"])
    second = assess_complexity("Create a, then b, then verify it", ["FILE_WRITE"])
    assert first == second  # byte-identical re-runs
    assert first["multi_step"] is True and first["ambiguous"] is True
    assert first["dependencies"] == 2
    assert assess_complexity("hi")["score"] <= 1


def test_risk_separate_from_depth():
    assert assess_risk("calculate 2+2")["tier"] == "LOW"
    assert assess_risk("delete everything now")["tier"] == "HIGH"
    assert assess_risk("Click the Save button")["tier"] == "MEDIUM"
    # Same complexity, different risk -> same mode family, risk tracked.
    simple_high = select_mode({"score": 1, "capabilities": ["FILE_WRITE"],
                               "actions": 1, "length": 20, "clauses": 1,
                               "ambiguous": False}, {"tier": "HIGH"})
    assert simple_high["mode"] in ("DEEP", "STANDARD")


def test_modes_exhaustive_and_budgets_ordered():
    assert MODES == ("DETERMINISTIC", "LIGHT", "STANDARD", "DEEP", "EXPERT")
    from cognition.reasoning.controller import _BUDGETS

    tokens = [_BUDGETS[m]["max_tokens"] for m in MODES]
    assert tokens == sorted(tokens)
    assert all(set(_BUDGETS[m]) == {"max_tokens", "timeout_s", "max_passes",
                                    "max_context_chars", "max_tool_calls"}
               for m in MODES)


# --------------------------------------------------
# model unavailable / provider switching
# --------------------------------------------------
def test_model_unavailable_honest():
    controller = ControllerStub(StubModels(models=[]))
    decision = controller.decide("Explain black holes in depth with math")
    assert decision["model"] == "" and decision["provider"] == ""
    outcome = controller.reason_budgeted("hi", decision)
    assert outcome["status"] == "failed"


def test_provider_switching_respected():
    stub = StubModels()
    stub.provider_pref = "builtin"
    controller = ControllerStub(stub)
    decision = controller.decide("Explain black holes with full rigor")
    assert decision["provider"] == "builtin"
    assert decision["model"] in ("tiny-100m", "mid-1b")


def test_single_model_uses_budgets_not_invention():
    controller = _controller()
    controller.models._models = [controller.models._models[0]]
    for mode in ("LIGHT", "STANDARD", "DEEP"):
        routed = controller.select_model(mode)
        assert routed["model"] == "tiny-100m"


# --------------------------------------------------
# budget enforcement / timeout / pass limits
# --------------------------------------------------
def test_budget_enforced_outside_model():
    controller = _controller()
    decision = controller.decide("what is your name?", is_question=True)
    outcome = controller.reason_budgeted("what is your name?", decision)
    assert outcome["status"] == "completed"
    assert outcome["passes"] == 1
    call = controller.models.calls[-1]
    assert call["timeout_s"] == 15
    assert call["kwargs"]["options"] == {"num_predict": 64}
    det = controller.decide("calculate 25 * 4")
    skipped = controller.reason_budgeted("calculate 25 * 4", det)
    assert skipped["status"] == "skipped" and skipped["passes"] == 0
    assert controller.models.calls and len(controller.models.calls) == 1  # no new call


def test_timeout_propagates_as_failure():
    controller = _controller()

    class Slow(StubModels):
        def generate(self, prompt, model=None, timeout_s=None, **kwargs):
            raise TimeoutError("slow model")

    controller.models = Slow()
    decision = controller.decide("Explain time dilation", is_question=True)
    outcome = controller.reason_budgeted("Explain time dilation", decision)
    assert outcome["status"] == "failed"
    assert "slow" in outcome["error"]


def test_multi_pass_limit_and_summary_only():
    controller = _controller()
    decision = controller.decide("x" * 10, context={"recent_failures": 5})
    decision["mode"] = "EXPERT"
    from cognition.reasoning.controller import _BUDGETS

    decision["budget"] = dict(_BUDGETS["EXPERT"])
    outcome = controller.reason_budgeted("hard problem", decision)
    assert outcome["status"] == "completed"
    assert outcome["passes"] <= 4
    assert len(outcome["summary"]) <= 500
    assert "trace" not in outcome and "chain" not in str(outcome).lower()


# --------------------------------------------------
# world shortcut / memory-aware / experience promotion
# --------------------------------------------------
def test_world_shortcut_skips_model():
    class Resolver:
        def answer(self, question):
            return {"status": "answered", "answer": "Running: notepad.",
                    "evidence": [{"verified": True}]}

    controller = _controller()
    decision = controller.decide("What application is currently running?",
                                 context={"world_resolver": Resolver()})
    assert decision["mode"] == "DETERMINISTIC"
    assert decision["shortcut"] == "world"
    assert "notepad" in decision["world_answer"]
    before = len(controller.models.calls)
    assert controller.reason_budgeted("q", decision)["status"] == "skipped"
    assert len(controller.models.calls) == before


def test_world_unverified_no_shortcut():
    class Resolver:
        def answer(self, question):
            return {"status": "answered", "answer": "maybe notepad",
                    "evidence": [{"verified": False}]}

    decision = _controller().decide(
        "What application is currently running?",
        context={"world_resolver": Resolver()})
    assert decision["shortcut"] == ""


def test_experience_promotion_bounded():
    controller = _controller()
    base = controller.decide("Create a file called x.txt")
    promoted = controller.decide(
        "Create a file called x.txt",
        context={"experience_stats": {"FILE_WRITE": 0.1},
                 "recent_failures": 2})
    order = list(MODES)
    assert order.index(promoted["mode"]) >= order.index(base["mode"])
    assert order.index(promoted["mode"]) - order.index(base["mode"]) <= 1
    assert "promotion" in promoted["reason"]


def test_conversation_isolation():
    first = _controller().decide("hi", is_question=True)
    second = _controller().decide("hi", is_question=True)
    assert first["mode"] == second["mode"] == "LIGHT"
    assert first["budget"] == second["budget"]


# --------------------------------------------------
# strategy choice + security isolation
# --------------------------------------------------
def test_strategy_choice_uses_decision_engine():
    controller = _controller()
    result = controller.choose_strategy([
        {"mode": "LIGHT", "latency_s": 2.0, "model_available": True,
         "verification": "weak", "risk": "LOW"},
        {"mode": "DEEP", "latency_s": 30.0, "model_available": True,
         "verification": "strong", "risk": "LOW"},
    ], experience_stats={"LIGHT": 0.9, "DEEP": 0.9})
    assert result["choice"]["mode"] in ("LIGHT", "DEEP")
    assert len(result["scores"]) == 2
    assert controller.choose_strategy([])["choice"] is None
    assert controller.choose_strategy([{"mode": "BOGUS"}])["choice"] is None


def test_security_isolation_no_authorization():
    controller = _controller()
    decision = controller.decide("delete everything with rm -rf / now")
    assert decision["mode"] in ("DEEP", "EXPERT")
    assert "policy" not in str(decision).lower()
    assert "approv" not in str(decision).lower()
    assert set(decision) >= {"mode", "model", "provider", "reason",
                             "budget", "risk", "complexity", "signals",
                             "capabilities", "shortcut"}


# --------------------------------------------------
# Brain integration shape
# --------------------------------------------------
def test_brain_decision_shape(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    decision = brain.decide_reasoning("calculate 25 * 4")
    assert decision["mode"] == "DETERMINISTIC"
    assert set(decision) >= {"mode", "model", "provider", "reason",
                             "budget", "risk"}
    assert brain.last_reasoning["mode"] == "DETERMINISTIC"
    report = brain.run_cycle("calculate 25 * 4")
    assert report["status"] == "completed"
    assert report["reasoning"]["mode"] == "DETERMINISTIC"
    assert brain.last_reasoning["mode"] == "DETERMINISTIC"


def test_brain_run_cycle_standard_uses_budget(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_WORLD_PATH", str(tmp_path / "world.json"))
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    # Conversational path: decision recorded, budget positive.
    brain.think("What is the capital of France?")
    assert brain.last_reasoning["mode"] in ("LIGHT", "STANDARD")
    assert brain.last_reasoning["budget"]["max_tokens"] > 0
    # Task path with capabilities: reasoning key present with budget.
    report = brain.run_cycle("Create a file called rcbudget.txt with content hi")
    assert report["status"] == "completed"
    assert report["reasoning"]["mode"] in ("STANDARD", "DEEP")
    assert report["reasoning"]["budget"]["max_tokens"] > 0
    try:
        from abilities.files.file_ability import _workspace

        target = _workspace() / "rcbudget.txt"
        if target.exists():
            target.unlink()
    except Exception:
        pass


# --------------------------------------------------
# UI / HUD snapshot
# --------------------------------------------------
def test_ui_hud_reasoning_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    from interface.app_controller import HerculeAppController
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    assert controller.snapshot()["reasoning"]["mode"] == "UNKNOWN"
    services["brain"].decide_reasoning("calculate 25 * 4")
    snap = controller.reasoning_snapshot()
    assert snap["mode"] == "DETERMINISTIC"
    assert "tok" in snap["budget_summary"]
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
        assert "reasoning" in app.reasoning_var.get().lower()
        assert app.reasoning_text_var.get().startswith("model:")
    finally:
        root.destroy()
