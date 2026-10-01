from __future__ import annotations
"""Phase M.1: data safety & evaluation isolation.

Proves the production-overwrite incident class cannot recur:
fail-closed guard, bound (non-lazy) save paths, write-guard
violations, synthetic sentinel immutability, cross-suite and
parallel isolation, baseline integrity. Never touches real
production data; never reconstructs lost records.
"""

import json

import pytest

from system.state_guard import (
    StateIsolationError,
    check_state_write,
    describe_isolation,
)


# ---------- fail-closed configuration ----------

def test_guard_inactive_by_default(monkeypatch):
    monkeypatch.delenv("HERCULE_TEST_GUARD", raising=False)
    assert check_state_write("data/memory/experiences.json", owner="t") == \
        "data/memory/experiences.json"


def test_guard_fail_closed_without_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HERCULE_TEST_GUARD", "1")
    monkeypatch.delenv("HERCULE_TEST_STATE_DIR", raising=False)
    with pytest.raises(StateIsolationError, match="HERCULE_TEST_STATE_DIR"):
        check_state_write(str(tmp_path / "x.json"), owner="experience")


def test_guard_rejects_outside_write_with_context(monkeypatch, tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("HERCULE_TEST_GUARD", "1")
    monkeypatch.setenv("HERCULE_TEST_STATE_DIR", str(state))
    outside = tmp_path / "prod" / "experiences.json"
    with pytest.raises(StateIsolationError) as info:
        check_state_write(str(outside), owner="experience")
    message = str(info.value)
    assert str(outside) in message
    assert str(state) in message
    assert "HERCULE_EXPERIENCE_STORE" in message
    assert check_state_write(str(state / "experiences.json"),
                             owner="experience")


def test_describe_isolation_never_raises(monkeypatch):
    monkeypatch.delenv("HERCULE_TEST_GUARD", raising=False)
    assert describe_isolation()["guard_active"] is False


# ---------- bound (non-lazy) save paths ----------

def test_experience_bound_path_survives_env_change(monkeypatch, tmp_path):
    from cognition.experience.experience_manager import ExperienceManager

    store_a = tmp_path / "a" / "experiences.json"
    store_b = tmp_path / "b" / "experiences.json"
    monkeypatch.setenv("HERCULE_EXPERIENCE_STORE", str(store_a))
    manager = ExperienceManager()
    assert manager.load(str(store_a)) == 0
    assert manager.store_path == str(store_a)
    # Ambient environment changes AFTER binding must not move saves.
    monkeypatch.setenv("HERCULE_EXPERIENCE_STORE", str(store_b))
    monkeypatch.setenv("HERCULE_MEMORY_DIR", str(tmp_path / "b"))
    assert manager.save() is True
    assert store_a.exists() and not store_b.exists()


def test_unbound_experience_save_refuses():
    from cognition.experience.experience_manager import ExperienceManager

    assert ExperienceManager().save() is False


def test_production_manager_immune_to_evaluator(tmp_path):
    from cognition.experience.experience_manager import ExperienceManager

    prod = tmp_path / "prod" / "experiences.json"
    prod.parent.mkdir(parents=True, exist_ok=True)
    prod.write_text(json.dumps({"version": 1, "records": []}), encoding="utf-8")
    production = ExperienceManager()
    assert production.load(str(prod)) == 0
    evaluator = ExperienceManager()
    eval_store = tmp_path / "eval" / "experiences.json"
    assert evaluator.load(str(eval_store)) == 0
    evaluator.record_rich("eval goal", capabilities=["MATH"],
                          abilities=["mathematics"],
                          verification={"passed_steps": 1}, status="completed",
                          task_id="e-1")
    assert evaluator.save() is True
    assert production.save() is True
    assert len(json.loads(prod.read_text())["records"]) == 0
    assert len(json.loads(eval_store.read_text())["records"]) == 1


# ---------- synthetic sentinel immutability ----------

def _math_tasks():
    from evaluation.framework.datasets.uai_core import uai_core_tasks

    return [t for t in uai_core_tasks()
            if t.task_id in ("uai-core-math-001", "uai-core-math-002")]


def test_evaluation_leaves_sentinel_untouched(tmp_path):
    from evaluation.framework.adapters import HermeticEvalAdapter
    from evaluation.framework.config import EvalConfig
    from evaluation.framework.runner import EvaluationRunner

    sentinel = tmp_path / "prod" / "experiences.json"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "records": [{"experience_id": "sentinel-1"}]}
    sentinel.write_text(json.dumps(payload), encoding="utf-8")
    digest = sentinel.read_bytes()
    adapter = HermeticEvalAdapter()
    try:
        run = EvaluationRunner(adapter, EvalConfig(live=False)).run_suite(
            _math_tasks(), scope="sentinel")
        assert run.counts["passed"] == 2
        # Learning happened — inside evaluation state, not the sentinel.
        from pathlib import Path

        eval_records = json.loads(
            (Path(adapter.state_dir) / "memory" / "experiences.json").read_text(
                encoding="utf-8"))
        assert len(eval_records.get("records", [])) >= 2
    finally:
        adapter.close()
    assert sentinel.read_bytes() == digest


# ---------- cross-suite isolation (A-B-A determinism) ----------

def _run_scope(task_ids, scope):
    from evaluation.framework.adapters import HermeticEvalAdapter
    from evaluation.framework.config import EvalConfig
    from evaluation.framework.registry import suite_tasks
    from evaluation.framework.runner import EvaluationRunner

    pool = {t.task_id: t for sid in ("uai_core", "uai_research")
            for t in suite_tasks(sid)}
    tasks = [pool[tid] for tid in task_ids]
    adapter = HermeticEvalAdapter()
    try:
        run = EvaluationRunner(adapter, EvalConfig(live=False)).run_suite(
            tasks, scope=scope)
        return run, adapter.state_dir
    finally:
        adapter.close()


def test_cross_suite_isolation_aba():
    math_ids = ["uai-core-math-001", "uai-core-math-002"]
    research_ids = ["uai-research-unavail-004", "uai-research-empty-005"]
    run_a1, dir_a1 = _run_scope(math_ids, "iso-a1")
    run_b, dir_b = _run_scope(research_ids, "iso-b")
    run_a2, dir_a2 = _run_scope(math_ids, "iso-a2")
    assert dir_a1 != dir_b != dir_a2 and dir_a1 != dir_a2
    assert run_a1.counts == run_a2.counts
    assert [(r.task_id, r.outcome.value, r.score) for r in run_a1.results] == \
           [(r.task_id, r.outcome.value, r.score) for r in run_a2.results]
    assert run_b.counts["passed"] == 2


# ---------- parallel-run state independence ----------

def test_parallel_runs_isolated():
    from evaluation.framework.adapters import HermeticEvalAdapter

    first = HermeticEvalAdapter()
    second = HermeticEvalAdapter()
    try:
        assert first.state_dir != second.state_dir
    finally:
        first.close()
        second.close()


# ---------- baseline integrity: results != runtime memory ----------

def test_results_separate_from_runtime_state(tmp_path):
    from evaluation.framework.adapters import HermeticEvalAdapter
    from evaluation.framework.config import EvalConfig
    from evaluation.framework.result import results_dir
    from evaluation.framework.runner import EvaluationRunner

    adapter = HermeticEvalAdapter()
    try:
        run = EvaluationRunner(adapter, EvalConfig(live=False)).run_suite(
            _math_tasks()[:1], scope="integrity")
        assert run.counts["passed"] == 1
        assert str(results_dir()) not in adapter.state_dir
        assert adapter.state_dir not in str(results_dir())
    finally:
        adapter.close()
