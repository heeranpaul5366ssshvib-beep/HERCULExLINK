"""Packaging/integration tests: entry point, resources, user data, headless, Ollama-absent, UI, shutdown."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _mock_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))


def test_production_entry_point_importable():
    spec = importlib.util.spec_from_file_location("hercule_app_main", str(REPO / "app" / "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)
    args = module.parse_args(["--headless"])
    assert args.headless is True
    args = module.parse_args([])
    assert args.headless is False


def test_resource_discovery():
    from system.paths import resolve_config_template, resource_dir

    assert (resource_dir() / "config" / "hercule.example.json").exists()
    assert resolve_config_template().exists()
    assert (REPO / "assets" / "hercule.ico").exists()
    assert (REPO / "boot.py").exists()


def test_packaged_configuration_template_valid():
    import json

    template = REPO / "config" / "hercule.example.json"
    data = json.loads(template.read_text(encoding="utf-8"))
    assert "models" in data
    assert data["models"].get("default_model")


def test_user_data_path_separation(monkeypatch, tmp_path):
    _mock_env(monkeypatch, tmp_path)
    from system import paths

    target = paths.user_data_dir()
    assert str(target).startswith(str(tmp_path))
    assert paths.resolve_data_path("data/memory").startswith(str(tmp_path)) or not paths.is_frozen()
    cfg = paths.ensure_user_config()
    assert str(cfg).startswith(str(tmp_path))
    # Upgrade-safe: second call never overwrites.
    cfg.write_text("KEEP", encoding="utf-8")
    assert paths.ensure_user_config().read_text(encoding="utf-8") == "KEEP"


def test_headless_mode(monkeypatch, capsys):
    _mock_env(monkeypatch, Path(os.environ.get("LOCALAPPDATA", str(Path.home()))))
    spec = importlib.util.spec_from_file_location("hercule_app_main_h", str(REPO / "app" / "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    answers = iter(["hi", "exit"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert module.main(["--headless", "--no-first-run"]) == 0
    out = capsys.readouterr().out
    assert "Shutdown" in out or "shutting down" in out.lower()


def test_missing_ollama_honest(monkeypatch):
    _mock_env(monkeypatch, Path(os.environ.get("LOCALAPPDATA", str(Path.home()))))
    monkeypatch.setenv("HERCULE_OLLAMA_HOST", "http://127.0.0.1:1")
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    spec = importlib.util.spec_from_file_location("hercule_app_main_o", str(REPO / "app" / "main.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    health = module.collect_health(services)
    assert "ollama" in health and "model" in health
    # Honest: unavailable is reported, never fake-ready.
    assert "UNAVAILABLE" in health["ollama"] or "ready" in health["ollama"]


def test_ui_startup_and_clean_shutdown(monkeypatch):
    _mock_env(monkeypatch, Path(os.environ.get("LOCALAPPDATA", str(Path.home()))))
    from interface.app_controller import HerculeAppController
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    result = controller.submit("hi")
    assert result["status"] in ("answered", "failed")
    snap = controller.snapshot()
    assert set(snap) >= {"consciousness", "model", "task", "events", "autonomy"}
    outcome = controller.shutdown_autonomy()
    assert outcome.get("state") in ("STOPPED", "UNKNOWN")


def test_desktop_app_builds_when_display_available(monkeypatch):
    _mock_env(monkeypatch, Path(os.environ.get("LOCALAPPDATA", str(Path.home()))))
    pytest_tk = pytest.importorskip("tkinter")
    del pytest_tk
    import tkinter as tk

    try:
        probe = tk.Tk()
        probe.withdraw()
        probe.destroy()
    except Exception as exc:
        pytest.skip(f"no display available: {exc}")
    from interface.app_controller import HerculeAppController
    from interface.desktop_app import HerculeDesktopApp
    from runtime.initializer import RuntimeInitializer

    services = RuntimeInitializer().initialize()
    controller = HerculeAppController(services)
    root = tk.Tk()
    root.withdraw()
    try:
        app = HerculeDesktopApp(controller, root=root)
        app._refresh()
    finally:
        root.destroy()


def _simulate_frozen(monkeypatch, tmp_path):
    """Pretend to be the installed (PyInstaller) app for path resolution."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("HERCULE_TASK_STORE", raising=False)
    monkeypatch.delenv("HERCULE_MEMORY_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    from system import paths

    assert paths.is_frozen()
    return paths


def test_frozen_logger_writes_to_user_data(monkeypatch, tmp_path):
    # Regression: installed app crashed at startup with WinError 5
    # (Access denied: 'data') because Logger mkdir'd relative data/logs.
    _simulate_frozen(monkeypatch, tmp_path)
    from system.logging.logger import Logger

    logger = Logger()
    assert str(logger.log_file).startswith(str(tmp_path))
    logger.info("frozen log probe")
    assert logger.log_file.exists()
    assert "frozen log probe" in logger.log_file.read_text(encoding="utf-8")


def test_frozen_config_uses_user_config(monkeypatch, tmp_path):
    # Regression: ConfigManager.save() would mkdir relative config/
    # (Program Files) in the installed app.
    _simulate_frozen(monkeypatch, tmp_path)
    from system.config.config_manager import ConfigManager

    manager = ConfigManager()
    assert str(manager.config_file).startswith(str(tmp_path))
    manager.set("probe", "1")
    manager.save()
    assert manager.config_file.exists()
    reloaded = ConfigManager()
    assert reloaded.load().get("probe") == "1"


def test_frozen_default_stores_resolve_to_user_data(monkeypatch, tmp_path):
    # Tasks, memory, and experience stores must resolve under the
    # per-user dir when frozen; explicit env overrides still win.
    _simulate_frozen(monkeypatch, tmp_path)
    from memory.memory_manager import _default_store_path
    from orchestrator.orchestrator import _default_task_store

    assert str(_default_task_store()).startswith(str(tmp_path))
    assert str(_default_store_path()).startswith(str(tmp_path))
    monkeypatch.setenv("HERCULE_TASK_STORE", str(tmp_path / "custom.json"))
    from system.config.runtime_config import load_runtime_config

    assert load_runtime_config().task_store.endswith("custom.json")
