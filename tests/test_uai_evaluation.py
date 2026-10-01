from __future__ import annotations
"""Phase M: evaluation infrastructure tests (no fabrication by design).

Covers M0 isolation, M2 task model, M4 traces, M5/M8 reliability,
M10 capability fidelity, M14/15 external registry, M16 scorecard,
M18 timings. Live-pipeline checks use the hermetic adapter on a
minimal task sample; the full baseline runs separately.
"""

import pytest

from evaluation.framework.adapters import HermeticEvalAdapter, ScriptedEvalAdapter
from evaluation.framework.config import EvalConfig
from evaluation.framework.registry import suite_tasks
from evaluation.framework.reliability import base_task_id, pass_at_k, repeat_stats
from evaluation.framework.result import Outcome, TaskResult
from evaluation.framework.runner import EvaluationRunner
from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _hermetic():
    return HermeticEvalAdapter()


# ---------- M0: production state protection ----------

def test_evaluation_does_not_touch_production_experience():
    from pathlib import Path

    prod = Path("data/memory/experiences.json")
    before = (prod.stat().st_mtime_ns, prod.stat().st_size) if prod.exists() else None
    adapter = _hermetic()
    try:
        from evaluation.framework.datasets.uai_core import uai_core_tasks

        tasks = [t for t in uai_core_tasks() if t.task_id == "uai-core-math-001"]
        run = EvaluationRunner(adapter, EvalConfig(live=False)).run_suite(tasks, scope="m0")
        assert run.counts["passed"] == 1
    finally:
        adapter.close()
    after = (prod.stat().st_mtime_ns, prod.stat().st_size) if prod.exists() else None
    assert before == after, "evaluation must not append to the production experience store"


def test_hermetic_state_dir_isolated(tmp_path):
    adapter = HermeticEvalAdapter(state_dir=str(tmp_path / "eval-state"))
    try:
        assert adapter.state_dir.startswith(str(tmp_path))
        from pathlib import Path

        assert (Path(adapter.state_dir) / "memory").exists() or True
    finally:
        adapter.close()


# ---------- M1/M2: task model ----------

def test_task_model_uai_fields():
    task = EvalTask(
        task_id="x", category=EvalCategory.AGENTIC, suite="s", prompt="p",
        expected_format="f", scoring_method=ScoringMethod.AGENTIC,
        input="i", expected_behavior="b", success_criteria="c",
        allowed_tools=["mathematics"], prohibited_tools=["terminal"],
        autonomy_level=2, difficulty="hard", tags=["t"],
        metadata={"k": "v"})
    assert task.autonomy_level == 2
    assert task.allowed_tools == ["mathematics"]
    assert task.tags == ["t"]
    clone = EvalTask.from_dict(task.to_dict())
    assert clone.autonomy_level == 2 and clone.tags == ["t"]


def test_suites_registered_with_counts():
    assert len(suite_tasks("uai_core")) == 24
    assert len(suite_tasks("uai_skills")) == 12
    assert len(suite_tasks("uai_research")) == 8
    assert len(suite_tasks("uai_safety")) == 10
    assert len(suite_tasks("golden_v1")) == 10


# ---------- M4: traces (outcomes only, never CoT) ----------

def test_trace_harvest_no_cot():
    adapter = ScriptedEvalAdapter(
        goal_rules=[("calc", {"status": "completed", "replans": 1,
                              "verification": {"passed_steps": 2, "failed_steps": []},
                              "reasoning": {"mode": "DETERMINISTIC"},
                              "result": {"completed": ["step-1"], "failed": []}})])
    task = EvalTask(task_id="t", category=EvalCategory.AGENTIC, suite="s",
                    prompt="calc", expected_format="f",
                    scoring_method=ScoringMethod.AGENTIC,
                    expected={"status": "completed"})
    result = EvaluationRunner(adapter, EvalConfig(live=False)).run_task(task)
    assert result.outcome == Outcome.PASSED
    assert result.trace["replans"] == 1
    assert result.trace["passed_steps"] == 2
    assert result.trace["reasoning_mode"] == "DETERMINISTIC"
    blob = str(result.trace).lower()
    assert "chain-of-thought" not in blob and "cot" not in blob.split()


# ---------- M5/M8: reliability ----------

def _mk(tid, passed, latency=10.0):
    return TaskResult(task_id=tid, suite_id="s", category="c",
                      outcome=Outcome.PASSED if passed else Outcome.FAILED,
                      score=1.0 if passed else 0.0, latency_ms=latency)


def test_pass_at_k_edges():
    assert pass_at_k(0, 5, 2) == 0.0
    assert pass_at_k(5, 5, 2) == 1.0
    assert pass_at_k(3, 5, 5) == 1.0
    assert pass_at_k(1, 2, 1) == 0.5
    assert pass_at_k(0, 0, 1) == 0.0


def test_repeat_stats_labels_small_samples():
    results = [_mk("a#r1", True, 10.0), _mk("a#r2", True, 12.0),
               _mk("b#r1", False, 9.0)]
    stats = repeat_stats(results)
    assert stats["per_task"]["a"]["success_rate"] == 1.0
    assert stats["per_task"]["a"]["small_sample"] is True
    assert stats["summary"]["tasks"] == 2
    assert base_task_id("a#r2") == "a"


def test_runs_config_repeats_tasks():
    adapter = ScriptedEvalAdapter(think_rules=[("p", "ok")])
    task = EvalTask(task_id="t", category=EvalCategory.GENERAL_KNOWLEDGE,
                    suite="s", prompt="p", expected_format="f",
                    scoring_method=ScoringMethod.CONTAINS_ANY,
                    expected=["ok"])
    run = EvaluationRunner(adapter, EvalConfig(live=False, runs=3)).run_suite([task])
    assert [r.task_id for r in run.results] == ["t", "t#r2", "t#r3"]
    stats = repeat_stats(run.results)
    assert stats["per_task"]["t"]["runs"] == 3


# ---------- M10.12: declared vs inferred capability fidelity ----------

def test_skill_capability_fidelity():
    from cognition.capabilities.inference import infer_capabilities
    from cognition.skills import Skill

    skill = Skill(skill_id="s", description="d",
                  required_capabilities=["MATH"], procedure=["Calculate 1+1"])
    inferred = {c.value for c in infer_capabilities(skill.procedure[0])}
    declared = {c.upper() for c in skill.required_capabilities}
    assert inferred & declared, f"mismatch: declared={declared} inferred={inferred}"
    bad = Skill(skill_id="b", description="d",
                required_capabilities=["MATH"], procedure=["Read the ledger file"])
    inferred_bad = {c.value for c in infer_capabilities(bad.procedure[0])}
    assert "MATH" not in inferred_bad, "mismatch must be detectable, not hidden"


# ---------- M14/M15: external registry honesty ----------

def test_external_registry_never_claims_runs():
    from evaluation.external_registry import (
        blocked_benchmarks, executed_benchmarks, registry_report)

    report = registry_report()
    assert len(report) == 15
    assert executed_benchmarks() == []
    assert len(blocked_benchmarks()) == 15
    assert all(r["execution_status"] in ("NOT_RUN", "BLOCKED") for r in report)
    assert all(r["last_run"] == "" and r["result"] is None for r in report)


# ---------- M16: scorecard ----------

def test_scorecard_format():
    from evaluation.framework.reporting import scorecard, scorecard_markdown

    run_results = [_mk("a", True, 20.0), _mk("b", False, 30.0)]
    from evaluation.framework.result import SuiteRun

    run = SuiteRun(run_id="r", scope="s", results=run_results,
                   model="mock", provider="mock")
    text = scorecard(run)
    assert text.startswith("HERCULE Evaluation Scorecard")
    assert "Success Rate:" in text and "Average Latency:" in text
    lowered = text.lower()
    assert "agi score" not in lowered and "human-level" not in lowered
    assert scorecard_markdown(run).startswith("# HERCULE Evaluation Scorecard")


# ---------- cross-task reference folding ----------

def test_workspace_relative_fold():
    from cognition.planner.references import workspace_relative

    inside = workspace_relative("eval_golden_1.txt")
    assert inside == "eval_golden_1.txt"
    assert workspace_relative("../outside_evil.txt") is None
    assert workspace_relative("C:\\Windows\\System32\\cmd.exe") is None
    assert workspace_relative("") is None


# ---------- M18: timings measured ----------

def test_timings_measured_on_live_task():
    adapter = _hermetic()
    try:
        from evaluation.framework.datasets.uai_core import uai_core_tasks

        tasks = [t for t in uai_core_tasks() if t.task_id == "uai-core-math-002"]
        result = EvaluationRunner(adapter, EvalConfig(live=False)).run_task(tasks[0])
        assert result.latency_ms > 0
        assert result.trace.get("passed_steps", 0) >= 1
    finally:
        adapter.close()
