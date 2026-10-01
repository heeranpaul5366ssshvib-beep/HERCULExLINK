"""Phase M-B: planner/brain integration, benchmark, evaluation, live path."""

import json

import pytest

from abilities.ability_manager import AbilityManager
from cognition.capabilities.hybrid import HybridMode, resolve_capabilities
from cognition.capabilities.registry import CapabilityRegistry
from cognition.capabilities.semantic import SemanticCapabilityProposer
from cognition.planner.planner import Planner
from cognition.planner.validation import validate_plan
from evaluation.benchmarks import BenchmarkCategory
from evaluation.engine import EvaluationEngine
from evaluation.semantic_eval import (
    calibration_buckets,
    load_capability_dataset,
    register_semantic_category,
    run_capability_benchmark,
    score_sets,
)
from runtime.initializer import RuntimeInitializer
from security.permissions.policy_manager import PolicyManager
from tests.support_semantic import SemanticMockModel, entry, payload


@pytest.fixture()
def stack():
    abilities = AbilityManager(PolicyManager())
    abilities.register_defaults()
    registry = CapabilityRegistry()
    registry.register_default_tools(abilities)
    return abilities, registry


def test_planner_legacy_byte_identical_without_semantic():
    planner = Planner()
    first = planner.create_capable_plan("ops", ["Read this file", "Calculate the totals"])
    assert all(s["semantic_report"] == {} for s in first)
    assert "optional_capabilities" not in first[0]
    legacy_caps = [s["required_capabilities"] for s in first]
    planner.configure_semantic(mode="hybrid")
    second = planner.create_capable_plan("ops", ["Read this file", "Calculate the totals"])
    assert [s["required_capabilities"] for s in second] == legacy_caps  # default off: identical
    third = planner.create_capable_plan("ops", ["Read this file"], semantic=False)
    assert third[0]["required_capabilities"] == ["FILE_READ"]


def test_planner_hybrid_populates_from_resolution(stack):
    abilities, registry = stack
    planner = Planner()
    model = SemanticMockModel(script=[("crash", payload(entry("SYSTEM_OBSERVE", 0.9, "diagnose")))])
    proposer = SemanticCapabilityProposer(model=model, allowed_capabilities=registry.capabilities())
    planner.configure_semantic(proposer=proposer, mode="hybrid", registry=registry,
                               policy=abilities.policy, ability_manager=abilities)
    plan = planner.create_capable_plan("ops", ["Inspect why my application crashes"], semantic=True)
    assert plan[0]["required_capabilities"] == ["SYSTEM_OBSERVE"]  # keyword misses, semantic finds
    assert plan[0]["semantic_report"]["mode"] == "hybrid"
    report = validate_plan(plan, registry, abilities.policy, ability_manager=abilities)
    assert report["valid"] is True
    assert report["metrics"]["semantic_confidence"] == 0.9
    assert report["metrics"]["semantic_rejected"] == 0


def test_planner_explicit_capabilities_validated(stack):
    abilities, registry = stack
    planner = Planner()
    plan = planner.create_capable_plan("ops", [{"description": "Read this file",
                                                "explicit_capabilities": ["FILE_READ", "ROCKET_CONTROL"]}])
    assert plan[0]["required_capabilities"] == ["FILE_READ"]
    assert plan[0]["explicit_capabilities"] == ["FILE_READ", "ROCKET_CONTROL"]
    report = validate_plan(plan, registry, abilities.policy, ability_manager=abilities)
    assert report["valid"] is True  # unknown explicit dropped by resolution


def test_brain_run_with_semantic_proposer():
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    orch = services["orchestrator"]
    model = SemanticMockModel(script=[("Calculate", payload(entry("MATH", 0.9, "numbers")))])
    proposer = SemanticCapabilityProposer(model=model)
    report = brain.run_cycle("Calculate the totals", payload_fn=lambda step: "6*7",
                             use_semantic=True, semantic_proposer=proposer,
                             correlation_id="sem-brain")
    assert report["status"] == "completed"
    assert brain._tracer.get("sem-brain") is not None


def test_brain_semantic_unconfigured_falls_back_deterministically():
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    report = brain.run_cycle("Calculate the totals", payload_fn=lambda step: "6*7",
                             use_semantic=True, correlation_id="sem-fallback")
    assert report["status"] == "completed"  # no proposer: deterministic, no crash


# --------------------------------------------------
# benchmark + evaluation
# --------------------------------------------------

def test_dataset_covers_required_categories():
    dataset = load_capability_dataset()
    assert len(dataset["cases"]) >= 12
    categories = {c["category"] for c in dataset["cases"]}
    for required in ("direct", "paraphrase", "implicit", "multi", "negation", "conditional",
                     "irrelevant", "ambiguous", "untrusted", "environment", "missing", "unavailable"):
        assert required in categories, required
    for case in dataset["cases"]:
        assert case["expected_required"] is not None


def _strategy_resolvers():
    from scripts.benchmark_capabilities import ScriptedModel, make_resolver
    dataset = load_capability_dataset()
    model = ScriptedModel(dataset)
    return {s: make_resolver(s, model, dataset) for s in ("deterministic", "hybrid", "shadow")}


def test_benchmark_metrics_and_shadow_equivalence():
    resolvers = _strategy_resolvers()
    dataset = load_capability_dataset()
    det = run_capability_benchmark(resolvers["deterministic"], dataset)
    hybrid = run_capability_benchmark(resolvers["hybrid"], dataset)
    shadow = run_capability_benchmark(resolvers["shadow"], dataset)
    assert det["cases"] == 15 and hybrid["cases"] == 15
    for report in (det, hybrid, shadow):
        for key in ("precision", "recall", "f1", "false_positives", "false_negatives", "mean_latency_ms"):
            assert report[key] >= 0
    # Shadow executes the deterministic set: identical metrics.
    assert shadow["precision"] == det["precision"] and shadow["recall"] == det["recall"]
    # Hybrid (validator-trimmed) beats raw recall-chasing on F1 here.
    assert hybrid["f1"] >= det["f1"]
    assert hybrid["false_negatives"] <= det["false_negatives"]
    assert score_sets(["A"], ["A"]) == {"precision": 1.0, "recall": 1.0, "f1": 1.0,
                                        "tp": 1, "fp": 0, "fn": 0}
    assert score_sets([], [])["f1"] == 1.0


def test_calibration_buckets_honest():
    proposals = [{"name": "A", "confidence": 0.95}, {"name": "B", "confidence": 0.6},
                 {"name": "C", "confidence": "bad"}]
    buckets = calibration_buckets(proposals, ["A"])
    assert buckets["0.90-1.00"] == {"correct": 1, "total": 1, "rate": 1.0}
    assert buckets["0.50-0.70"]["rate"] == 0.0
    assert set(buckets) == {"0.50-0.70", "0.70-0.90", "0.90-1.00"}


def test_evaluation_engine_category():
    from scripts.benchmark_capabilities import ScriptedModel, make_resolver
    dataset = load_capability_dataset()
    engine = EvaluationEngine()
    assert BenchmarkCategory.SEMANTIC_CAPABILITY_INFERENCE.value == "semantic_capability_inference"
    register_semantic_category(engine, make_resolver("hybrid", ScriptedModel(dataset), dataset))
    assert "semantic_capabilities" in engine.subsystems()
    evaluation = engine.evaluate("semantic_capabilities")
    assert evaluation.score >= 0.5 and evaluation.passed is True
    assert evaluation.metrics["false_positives"] >= 0


def test_live_path_with_real_manager_falls_back_safely():
    from models.model_manager import ModelManager
    manager = ModelManager()
    proposer = SemanticCapabilityProposer(model=manager, allowed_capabilities=["FILE_READ"])
    result = proposer.propose("Read this file")
    # MockAdapter output is not schema JSON: must fall back, never crash.
    assert result.fallback_used is True
    assert result.semantic_used is False
    assert any("MALFORMED" in e for e in result.errors)


def test_env_gated_real_model():
    import os
    model_id = os.environ.get("HERCULE_SEMANTIC_MODEL", "")
    if not model_id:
        pytest.skip("no operator-provided semantic model")
    raise AssertionError("unreachable without HERCULE_SEMANTIC_MODEL")
