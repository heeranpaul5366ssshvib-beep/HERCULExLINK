from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Semantic Capability Evaluation
Author: Heeran Paul
License: MIT
--------------------------------------------

Benchmark dataset loading, precision/recall/F1 scoring, confidence
calibration, and EvaluationEngine registration for the
SEMANTIC_CAPABILITY_INFERENCE category. No competing framework: the
existing engine, scorer shape, and benchmark registry are reused.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DATASET_PATH = (Path(__file__).resolve().parent.parent / "cognition" / "capabilities"
                / "datasets" / "capability_bench_v1.json")


def load_capability_dataset(path: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(path) if path else DATASET_PATH
    with open(target, encoding="utf-8") as handle:
        return json.load(handle)


def score_sets(predicted: List[str], expected: List[str]) -> Dict[str, float]:
    pred, exp = set(predicted), set(expected)
    tp = len(pred & exp)
    fp = len(pred - exp)
    fn = len(exp - pred)
    precision = tp / len(pred) if pred else (1.0 if not exp else 0.0)
    recall = tp / len(exp) if exp else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "tp": tp, "fp": fp, "fn": fn}


def run_capability_benchmark(
    resolve_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    dataset: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run every case through ``resolve_fn(case) -> {"required": [...],
    "optional": [...], "latency_ms": float, ...}`` and aggregate."""
    dataset = dataset or load_capability_dataset()
    cases: List[Dict[str, Any]] = []
    for case in dataset.get("cases", []):
        outcome = resolve_fn(case) or {}
        required = list(outcome.get("required", []))
        scores = score_sets(required, list(case.get("expected_required", [])))
        cases.append({"id": case.get("id"), "category": case.get("category"),
                      "predicted": required, "expected": list(case.get("expected_required", [])),
                      "latency_ms": round(float(outcome.get("latency_ms", 0.0)), 3),
                      "fallback_used": bool(outcome.get("fallback_used", False)),
                      "extra": {k: v for k, v in outcome.items()
                                if k not in ("required", "optional", "latency_ms", "fallback_used")},
                      **scores})
    n = len(cases)
    mean = lambda k: round(sum(c[k] for c in cases) / n, 3) if n else 0.0
    return {
        "dataset": dataset.get("name", ""), "cases": n,
        "precision": mean("precision"), "recall": mean("recall"), "f1": mean("f1"),
        "false_positives": sum(c["fp"] for c in cases),
        "false_negatives": sum(c["fn"] for c in cases),
        "fallbacks": sum(1 for c in cases if c["fallback_used"]),
        "mean_latency_ms": mean("latency_ms"),
        "results": cases,
    }


def calibration_buckets(proposals: List[Dict[str, Any]], hits: List[str]) -> Dict[str, Any]:
    """Confidence calibration: correctness rate per confidence bucket.

    ``proposals`` carry name+confidence; ``hits`` are the names judged
    correct. Reports measured correlation — never assumes calibration.
    """
    buckets = {"0.50-0.70": [0, 0], "0.70-0.90": [0, 0], "0.90-1.00": [0, 0]}
    for proposal in proposals:
        try:
            confidence = float(proposal.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        key = "0.50-0.70" if confidence < 0.7 else ("0.70-0.90" if confidence < 0.9 else "0.90-1.00")
        buckets[key][1] += 1
        if proposal.get("name") in set(hits):
            buckets[key][0] += 1
    return {k: {"correct": c, "total": t, "rate": round(c / t, 3) if t else None}
            for k, (c, t) in buckets.items()}


def register_semantic_category(engine: Any, resolve_fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """Register SEMANTIC_CAPABILITY_INFERENCE with an EvaluationEngine."""
    from evaluation.metrics import SubsystemScore

    def scorer(payload: Optional[Dict[str, Any]] = None) -> SubsystemScore:
        report = run_capability_benchmark(resolve_fn)
        passed = report["f1"] >= 0.5 and report["false_positives"] <= len(report["results"])
        return SubsystemScore("semantic_capabilities", report["f1"], passed,
                              {"precision": report["precision"], "recall": report["recall"],
                               "f1": report["f1"], "false_positives": report["false_positives"],
                               "false_negatives": report["false_negatives"],
                               "mean_latency_ms": report["mean_latency_ms"]},
                              f"{report['cases']} benchmark cases")
    engine.register("semantic_capabilities", scorer)
