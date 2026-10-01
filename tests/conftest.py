"""Phase G: hermetic test environment.

Local model backends (transformers weights, sentence-transformers,
Ollama server) vary by machine and must not be downloaded during unit
tests. Offline flags force cache-only loads: cached models stay
available, missing ones report unavailable honestly (which is exactly
what the degraded-provider tests assert). No test behavior is masked —
availability branches are covered explicitly in test_phase_g_*.
"""

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import pytest


@pytest.fixture(autouse=True)
def _isolated_world_store(tmp_path, monkeypatch):
    """Hermetic world model per test (v2).

    Brain reference resolution consults world entities, so a shared
    dev store would let one test's verified files leak into another
    test's anaphora. Each test gets a fresh store unless it sets
    HERCULE_WORLD_PATH itself (explicit monkeypatch wins).
    """
    monkeypatch.setenv("HERCULE_WORLD_PATH", str(tmp_path / "world.json"))


@pytest.fixture()
def isolated_runtime_state(tmp_path, monkeypatch):
    """Standard isolated persistent-state fixture (UAI Phase M.1).

    Redirects every mutable store — tasks, memory, experience,
    skills, world — into a per-test temporary directory and enables
    the fail-closed write guard, so guarded saves outside that
    directory raise StateIsolationError instead of touching
    production. Opt-in per test (pure unit tests need no filesystem
    state). Returns the state dir path.
    """
    from pathlib import Path

    root = Path(str(tmp_path)) / "hercule-state"
    (root / "memory").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERCULE_TASK_STORE", str(root / "tasks.json"))
    monkeypatch.setenv("HERCULE_MEMORY_DIR", str(root / "memory"))
    monkeypatch.setenv("HERCULE_EXPERIENCE_STORE",
                       str(root / "memory" / "experiences.json"))
    monkeypatch.setenv("HERCULE_SKILLS_STORE", str(root / "skills.json"))
    monkeypatch.setenv("HERCULE_WORLD_PATH", str(root / "world.json"))
    monkeypatch.setenv("HERCULE_TEST_GUARD", "1")
    monkeypatch.setenv("HERCULE_TEST_STATE_DIR", str(root))
    return root
