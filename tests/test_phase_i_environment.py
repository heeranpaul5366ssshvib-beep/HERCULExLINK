"""Phase I: environment validation, startup classes, asyncio config."""

import tomllib
from pathlib import Path

import pytest

from system.config.embedding_config import load_embedding_config, resolve_embedding_provider
from system.config.env_validation import (
    check_embedding_config,
    check_package,
    check_packages,
    validate_environment,
)
from system.startup_validation import (
    BACKEND_UNAVAILABLE,
    CONFIGURATION_ERROR,
    RUNTIME_FAILURE,
    StartupValidationError,
    classify_startup_error,
    validate_startup,
)


def test_python_and_required_packages():
    report = validate_environment()
    assert report["python"]["ok"] is True
    required = [p for p in report["packages"] if p["required"]]
    assert required
    assert all(p["installed"] and p["ok"] for p in required), [
        p for p in required if not (p["installed"] and p["ok"])
    ]
    assert report["vector_backend"]["ok"] is True
    assert report["embedding_backends"]["ok"] is True  # hash provider always available
    assert report["embedding_config"]["ok"] is True  # static default validation
    assert report["ok"] is True


def test_missing_package_reported_not_installed():
    entry = check_package("definitely-missing-pkg-xyz", "1.0", required=True)
    assert entry == {"name": "definitely-missing-pkg-xyz", "required": True, "installed": False,
                     "version": "", "minimum": "1.0", "ok": False, "detail": "not installed"}
    optional = check_package("definitely-missing-pkg-xyz", "1.0", required=False)
    assert optional["ok"] is True
    low = check_package("pytest", "99.0.0", required=True)
    assert low["installed"] is True and low["ok"] is False


def test_all_declared_floors_satisfiable():
    for entry in check_packages():
        if entry["required"]:
            assert entry["installed"], entry["name"]


def test_static_config_check_without_model_loads():
    ok = check_embedding_config({"mode": "test"})
    assert ok["ok"] is True and ok["mode"] == "test"
    bad = check_embedding_config({"provider": "telepathy", "mode": "test"})
    assert bad["ok"] is False and bad["code"] == "EMBEDDING_UNKNOWN_PROVIDER"


def test_startup_failure_classes():
    with pytest.raises(StartupValidationError) as config_err:
        validate_startup({"provider": "telepathy", "mode": "test"})
    assert config_err.value.failure_class == CONFIGURATION_ERROR
    with pytest.raises(StartupValidationError) as backend_err:
        validate_startup({"provider": "ollama", "mode": "offline"})
    assert backend_err.value.failure_class == BACKEND_UNAVAILABLE
    assert classify_startup_error(RuntimeError("boom")) == RUNTIME_FAILURE


def test_startup_success_and_static_path():
    provider, report = validate_startup({"mode": "test"})
    assert provider.model_id == "hercule-hash-test-v1"
    assert report["failure_class"] is None
    config = load_embedding_config({"mode": "test"}, env={})
    provider, report = resolve_embedding_provider(config, check_health=False)
    assert report["health_checked"] is False
    assert report["selected"]["provider"] == "hash"


def test_asyncio_scope_is_pinned_not_suppressed():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    scope = data["tool"]["pytest"]["ini_options"]["asyncio_default_fixture_loop_scope"]
    assert scope == "function"
