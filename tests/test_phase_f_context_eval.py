"""Phase F: context 2.0 budgets/priorities + evaluation + failure taxonomy."""

from cognition.context.context_engine import ContextEngine
from cognition.context.priority import BudgetConfig, PriorityClass, apply_budgets, classify_priority
from evaluation.benchmarks import BenchmarkCase, BenchmarkCategory, BenchmarkRegistry
from evaluation.engine import EvaluationEngine, build_baseline
from evaluation.failures import FailureCategory, FailureLedger, classify_failure
from evaluation.metrics import SubsystemScore, aggregate_scores, compute_task_quality
from cognition.task_manager.task_manager import TaskManager


def _ranked(n=8):
    return [{"source": "memory", "text": f"memory fact number {i} here", "relevance": 0.9 - i * 0.1} for i in range(n)]


def test_priority_classes_protect_critical_information():
    assert classify_priority({"source": "current_request", "relevance": 1.0}) == PriorityClass.CRITICAL
    assert classify_priority({"source": "system", "relevance": 0.1}) == PriorityClass.CRITICAL
    assert classify_priority({"source": "memory", "attention_score": 0.85}) == PriorityClass.IMPORTANT
    assert classify_priority({"source": "memory", "attention_score": 0.5}) == PriorityClass.RELEVANT
    assert classify_priority({"source": "memory", "attention_score": 0.2}) == PriorityClass.OPTIONAL
    assert classify_priority({"source": "memory", "attention_score": 0.01}) == PriorityClass.DISCARDABLE


def test_budgets_enforce_total_and_diagnostics():
    selected, diagnostics = apply_budgets(_ranked(), BudgetConfig(total_tokens=25, compress=False))
    assert len(selected) < 8
    assert any(d["action"] == "removed" for d in diagnostics)
    assert all("priority" in item for item in selected)


def test_per_source_caps_are_reported():
    items = _ranked(6) + [{"source": "tool", "text": "tool schema blob here", "relevance": 0.6}]
    selected, diagnostics = apply_budgets(items, BudgetConfig(total_tokens=1000, per_source_tokens={"memory": 12}, compress=False))
    assert any(d.get("reason", "").startswith("per-source cap") for d in diagnostics)


def test_oversized_context_keeps_critical_items():
    engine = ContextEngine(task_state={"goal": "Fix router"}, system={"mode": "safe"}, max_tokens=10000)
    payload = engine.build_context("x " * 500, budget_config=BudgetConfig(total_tokens=30))
    sources = {item["source"] for item in payload["items"]}
    assert "current_request" in sources  # critical request survives
    assert payload["token_usage"] <= 200  # protected overflow is bounded, not wild
    assert isinstance(payload["diagnostics"], list) and payload["diagnostics"]


def test_context_engine_default_path_is_unchanged():
    engine = ContextEngine(task_state={"goal": "Fix router"}, max_tokens=60)
    payload = engine.build_context("diagnose the router")
    assert payload["token_budget"] == 60
    assert payload["observability"]["item_count"] == len(payload["items"])
    assert "priorities" in payload and "diagnostics" in payload


def test_task_quality_keeps_underlying_metrics():
    manager = TaskManager()
    good = manager.create_task("Diagnose router", expected_result="fixed")
    manager.queue_task(good)
    manager.start(good)
    manager.complete(good, result="fixed")
    quality = compute_task_quality(manager.get(good))
    assert quality.score >= 0.8
    assert quality.as_dict()["verification"] == 1.0
    bad = manager.create_task("Broken task")
    manager.queue_task(bad)
    manager.start(bad)
    manager.fail(bad, "temporary model timeout")
    poor = compute_task_quality(manager.get(bad))
    assert poor.score < quality.score
    assert poor.error_rate > 0


def test_evaluation_engine_and_aggregation():
    engine = EvaluationEngine()
    engine.register("retrieval", lambda p: SubsystemScore("retrieval", 0.8, True, {"precision": 0.8}))
    engine.register("routing", lambda p: SubsystemScore("routing", 0.4, False, {"accuracy": 0.4}))
    outcome = engine.evaluate_all()
    assert outcome["score"] == 0.6
    assert outcome["passed"] is False
    assert len(outcome["subsystems"]) == 2
    assert aggregate_scores([])["score"] == 0.0


def test_benchmark_registry_runs_and_exports(tmp_path):
    registry = BenchmarkRegistry()
    registry.register(BenchmarkCase("kw", BenchmarkCategory.KNOWLEDGE_RETRIEVAL, lambda: {"passed": True, "recall": 1.0}))
    registry.register(BenchmarkCase("route", BenchmarkCategory.MODEL_ROUTING, lambda: {"passed": True}))
    summary = registry.run_all()
    assert summary["total"] == 2 and summary["passed"] == 2 and summary["pass_rate"] == 1.0
    scoped = registry.run_category(BenchmarkCategory.MODEL_ROUTING)
    assert scoped["total"] == 1
    exported = registry.export(tmp_path / "bench.json")
    assert exported.exists()


def test_failure_taxonomy_covers_repo_error_strings():
    assert classify_failure("Permission FILE_WRITE is not allowed").category == FailureCategory.PERMISSION
    assert classify_failure("Maximum retries exceeded.").code == "RECOVERY_EXHAUSTED"
    assert classify_failure("Maximum retries exceeded.").retryable is False
    assert classify_failure("Verification failed: expected X").category == FailureCategory.VERIFICATION
    assert classify_failure("temporary model timeout").category == FailureCategory.MODEL
    assert classify_failure("connection timeout").category == FailureCategory.NETWORK
    assert classify_failure("Invalid task transition").category == FailureCategory.INPUT
    assert classify_failure("weird unknown glitch").category == FailureCategory.INTERNAL


def test_failure_ledger_aggregates_recurring_failures():
    ledger = FailureLedger()
    ledger.record_error("temporary model timeout", task_id="t1")
    ledger.record_error("model unavailable", task_id="t2")
    ledger.record_error("Maximum retries exceeded.", task_id="t3")
    stats = ledger.statistics()
    assert stats["total"] == 3
    assert stats["by_category"]["model"] == 2
    assert stats["top_recurring"][0]["count"] == 2
    assert 0.0 <= stats["recovery_rate"] <= 1.0


def test_performance_baseline_records_stages():
    report = build_baseline({"context": lambda: {"items": 3}, "routing": lambda: {"model": "mock"}})
    assert report["total_ms"] >= 0
    assert {s["stage"] for s in report["stages"]} == {"context", "routing"}
    assert all(s["latency_ms"] >= 0 for s in report["stages"])
