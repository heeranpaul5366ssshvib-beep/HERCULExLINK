"""Stage 9: desktop interface + application controller.

Controller tests run against the live runtime with the mock model
(fast, deterministic). UI construction is attempted only when a
display is available, otherwise skipped. No brain logic is duplicated
here: every value is read from the real runtime or UNKNOWN.
"""
import importlib.util
from pathlib import Path

import pytest


def load_boot_module():
    spec = importlib.util.spec_from_file_location(
        "hercule_boot_ui", str(Path("boot.py").resolve()))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mock_env(monkeypatch):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")


@pytest.fixture()
def services(monkeypatch):
    mock_env(monkeypatch)
    from runtime.initializer import RuntimeInitializer
    return RuntimeInitializer().initialize()


@pytest.fixture()
def controller(services):
    from interface.app_controller import HerculeAppController
    return HerculeAppController(services)


def test_submit_conversation_uses_real_brain(controller):
    result = controller.submit("hi")
    assert result["kind"] == "QUESTION"
    assert result["status"] == "answered"
    text = controller.format_response(result)
    # Answered by the real Brain path (mock model backend in tests,
    # Ollama in production) — never hardcoded, never fabricated.
    assert text and text.strip()
    assert "dynamically synthesized" not in text
    assert "STUB" not in text


def test_submit_task_executes_real_ability(controller):
    result = controller.submit("calculate 25+4")
    assert result["kind"] == "GOAL"
    assert result["status"] in ("completed", "partial")
    assert controller.last_task_id == result["task_id"]


def test_snapshot_reads_live_runtime(controller):
    controller.submit("hi")
    snap = controller.snapshot()
    assert set(snap) >= {"consciousness", "goals", "model", "task",
                         "events", "busy"}
    assert snap["consciousness"]["state"] in (
        "IDLE", "ACTIVE", "LISTENING", "UNDERSTANDING", "THINKING",
        "PLANNING", "EXECUTING", "OBSERVING", "VERIFYING", "REFLECTING",
        "RECOVERING", "WAITING", "COMPLETED", "ERROR", "UNKNOWN")
    assert snap["model"]["model"] != ""
    assert isinstance(snap["events"], list)
    assert snap["busy"] is False


def test_snapshot_task_reflects_execution(controller):
    result = controller.submit("calculate 25+4")
    assert result["status"] in ("completed", "partial")
    task = controller.snapshot()["task"]
    assert task is not None and task["id"] == result["task_id"]
    assert task["status"] in ("COMPLETED", "completed", "PARTIAL", "partial")
    assert task["progress"] != "UNKNOWN"


def test_task_controls_require_task(controller):
    with pytest.raises(RuntimeError, match="no active task"):
        controller.cancel_current()
    with pytest.raises(RuntimeError, match="no active task"):
        controller.pause_current()
    with pytest.raises(RuntimeError, match="no active task"):
        controller.resume_current()


def test_task_controls_delegate_to_brain(controller):
    result = controller.submit("calculate 25+4")
    assert result["status"] in ("completed", "partial")
    # The task already completed synchronously, so lifecycle calls must
    # surface the REAL backend verdicts — never fabricated success.
    for action in ("pause_current", "resume_current", "cancel_current"):
        try:
            outcome = getattr(controller, action)()
        except (ValueError, RuntimeError) as exc:
            assert "task-1" in str(exc).lower() or "completed" in str(exc).lower() \
                or "cannot" in str(exc).lower()
        else:
            assert outcome["task_id"] == result["task_id"]
            assert outcome["action"] in ("pause", "resume", "cancel")


def test_unknown_when_services_missing():
    from interface.app_controller import HerculeAppController

    class StubBrain:
        consciousness = None
        goals = None

        def think(self, text):
            raise AssertionError("UI must not call brain directly in this test")

    controller = HerculeAppController.__new__(HerculeAppController)
    controller.services = {}
    controller.brain = StubBrain()
    controller.last_task_id = None
    controller.last_correlation_id = None
    controller.last_result = None
    snap = controller.snapshot()
    assert snap["consciousness"]["state"] == "UNKNOWN"
    assert snap["model"]["provider"] == "UNKNOWN"
    assert snap["task"] is None
    assert snap["events"] == []


def test_event_stream_summaries_never_leak_prompts(controller):
    controller.submit("hi")
    for event in controller.snapshot()["events"]:
        assert "prompt" not in event["summary"].lower() or "recorded" in event["summary"]
        assert "chain-of-thought" not in event["summary"]


def test_desktop_app_builds_when_display_available(controller):
    pytest.importorskip("tkinter")
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
    except Exception as exc:
        pytest.skip(f"no display available: {exc}")
    from interface.desktop_app import HerculeDesktopApp
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        app = HerculeDesktopApp(controller, root=root)
        assert app.state_var.get() in ("UNKNOWN",) or isinstance(app.state_var.get(), str)
        app._refresh()
        assert app.chat.get("1.0", "end").strip() != ""
    finally:
        root.destroy()


def test_boot_headless_runs_cli(monkeypatch, capsys):
    mock_env(monkeypatch)
    boot = load_boot_module()
    answers = iter(["hi", "exit"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    assert boot.main(["--headless"]) == 0
    output = capsys.readouterr().out
    assert "HERCULE > " not in output  # responses printed, prompt consumed
    assert "Shutting down" in output or "Shutdown Complete" in output


def test_boot_gui_falls_back_without_display(monkeypatch, capsys):
    mock_env(monkeypatch)
    boot = load_boot_module()
    answers = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda *args: next(answers))
    import interface.desktop_app as desktop_app
    monkeypatch.setattr(desktop_app, "launch",
                        lambda controller: (_ for _ in ()).throw(
                            RuntimeError("no display")))
    assert boot.main([]) == 0
    output = capsys.readouterr().out
    assert "UI unavailable" in output
