from __future__ import annotations
"""Phase L2/L3: authoritative ExperienceManager + storage isolation.

ONE shared store across Brain/Cognition/SkillManager; tmp-scoped
stores prove a fresh environment runs green without the accumulated
production history. Production files are never touched.
"""

import json

import pytest


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_DEFAULT_MODEL", "mock")
    monkeypatch.setenv("HERCULE_ALLOW_MOCK", "1")
    monkeypatch.setenv("HERCULE_TASK_STORE", ":memory:")
    monkeypatch.setenv("HERCULE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("HERCULE_EXPERIENCE_STORE",
                       str(tmp_path / "memory" / "experiences.json"))
    monkeypatch.setenv("HERCULE_SKILLS_STORE", str(tmp_path / "skills.json"))
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    return services, tmp_path


def test_single_authoritative_instance(isolated):
    services, _ = isolated
    exp = services["experience"]
    assert exp is not None
    assert services["brain"]._experience is exp
    assert services["cognition"].experience is exp
    assert services["skills"].experience is exp


def test_run_cycle_records_into_shared_store(isolated):
    services, _ = isolated
    report = services["brain"].run_cycle("calculate 31+31")
    assert report["status"] == "completed"
    records = services["experience"].query(limit=100000)
    assert any(r.task_id == report["task_id"] and r.outcome == "SUCCESS"
               for r in records)


def test_experience_persists_and_reloads(isolated):
    services, tmp_path = isolated
    services["brain"].run_cycle("calculate 32+32")
    path = tmp_path / "memory" / "experiences.json"
    assert path.exists()
    from cognition.experience.experience_manager import ExperienceManager

    fresh = ExperienceManager()
    assert fresh.load(str(path)) >= 1
    assert any(r.outcome == "SUCCESS" for r in fresh.query(limit=100000))


def test_fresh_environment_needs_no_prior_history(isolated):
    services, tmp_path = isolated
    # No accumulated history: proposals stay None, yet execution is green.
    assert services["experience"].query(limit=100000) == []
    assert services["experience"].propose_procedure("general") is None
    report = services["brain"].run_cycle("calculate 33+33")
    assert report["status"] == "completed"
    data = json.loads((tmp_path / "memory" / "experiences.json").read_text())
    assert len(data.get("records", [])) == 1


def test_config_storage_overrides(monkeypatch, tmp_path):
    from system.config.runtime_config import load_runtime_config

    monkeypatch.setenv("HERCULE_EXPERIENCE_STORE", str(tmp_path / "e.json"))
    monkeypatch.setenv("HERCULE_SKILLS_STORE", str(tmp_path / "s.json"))
    config = load_runtime_config()
    assert config.experience_store == str(tmp_path / "e.json")
    assert config.skills_store == str(tmp_path / "s.json")
    assert load_runtime_config().as_dict()["experience_store"] == str(tmp_path / "e.json")


def test_production_defaults_unchanged(monkeypatch):
    from system.config.runtime_config import load_runtime_config

    monkeypatch.delenv("HERCULE_EXPERIENCE_STORE", raising=False)
    monkeypatch.delenv("HERCULE_SKILLS_STORE", raising=False)
    monkeypatch.delenv("HERCULE_MEMORY_DIR", raising=False)
    config = load_runtime_config()
    assert config.experience_store == ""
    assert config.skills_store == ""
