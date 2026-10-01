from __future__ import annotations
"""N9-CAP Capability Matrix Evaluation (N9-CAP §7).

Expanded evaluation framework with fine-grained capability categories.
Each capability is evaluated independently with clear pass criteria.
"""

from .eval_harness import (
    SUITES, HARNESS_VERSION, build_suite, run_suite, run_all, verify_task,
    reference_predict, model_predict_factory
)
from .verifiers import verify_math, verify_json, verify_tool_call, verify_refusal
from .reasoning_format import (
    parse_structured_reasoning, validate_structured_reasoning,
    make_arithmetic_reasoning, make_tool_call_reasoning
)
from .generalization_eval import (
    GeneralizationTestCase, generate_all_heldout, evaluate_generalization
)

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# --------------------------------------------------
# Capability Categories (N9-CAP §7)

CAPABILITY_CATEGORIES = {
    "LANGUAGE": {
        "description": "Basic syntax, vocabulary, factual recall, instruction following",
        "suites": ["GENERAL"],
        "metrics": ["perplexity", "next_token_accuracy", "instruction_following_rate"],
    },
    "ARITHMETIC": {
        "description": "Exact arithmetic computation",
        "suites": ["MATH"],
        "metrics": ["exact_match", "partial_credit", "error_type_distribution"],
    },
    "SYMBOLIC_REASONING": {
        "description": "Logic, comparison, sequence induction, symbolic transformation",
        "suites": ["REASONING"],
        "metrics": ["exact_match", "pattern_recognition_rate"],
    },
    "STRUCTURED_REASONING": {
        "description": "OBSERVE/RELATE/PLAN/VERIFY/ANSWER format compliance",
        "suites": ["REASONING", "MATH", "ARC_STYLE"],
        "metrics": ["format_validity", "tag_completeness", "verification_accuracy"],
    },
    "CODE": {
        "description": "Python code generation, completion, debugging",
        "suites": ["CODING"],
        "metrics": ["syntax_validity", "test_pass_rate", "completion_rate"],
    },
    "PLANNING": {
        "description": "Task decomposition, step sequencing",
        "suites": ["AGENT"],
        "metrics": ["step_validity", "goal_achievement", "plan_coherence"],
    },
    "TOOL_USE": {
        "description": "Tool call proposal, argument formatting, result integration",
        "suites": ["TOOL_USE"],
        "metrics": ["call_validity", "arg_correctness", "result_integration"],
    },
    "VERIFICATION": {
        "description": "Self-verification, error detection, correction",
        "suites": ["RELIABILITY"],
        "metrics": ["verification_accuracy", "false_positive_rate", "correction_rate"],
    },
    "CORRECTION": {
        "description": "Error recognition and correction",
        "suites": ["RELIABILITY"],
        "metrics": ["correction_accuracy", "error_type_coverage"],
    },
    "ARC_REASONING": {
        "description": "Grid transformation, object detection, compositional transforms",
        "suites": ["ARC_STYLE"],
        "metrics": ["transform_accuracy", "compositional_generalization", "object_consistency"],
    },
    "GENERALIZATION": {
        "description": "Held-out compositional and distributional generalization",
        "suites": ["HELDOUT"],
        "metrics": ["exact_match", "partial_match", "generalization_gap"],
    },
}


# --------------------------------------------------
# Capability Matrix Evaluation

@dataclass
class CapabilityResult:
    """Result for a single capability category."""
    category: str
    score: float
    num_examples: int
    passed: int
    metrics: Dict[str, float]
    details: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CapabilityMatrix:
    """Complete capability matrix for a model checkpoint."""
    model_id: str
    checkpoint: str
    timestamp: str
    categories: Dict[str, CapabilityResult]
    overall_score: float
    generalization_gap: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "checkpoint": self.checkpoint,
            "timestamp": self.timestamp,
            "overall_score": self.overall_score,
            "generalization_gap": self.generalization_gap,
            "categories": {k: asdict(v) for k, v in self.categories.items()}
        }


def evaluate_capability_category(
    category: str,
    predict: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str = "unknown",
    checkpoint: str = "unknown",
    inference: Dict[str, Any] | None = None
) -> CapabilityResult:
    """Evaluate a single capability category."""
    cat_info = CAPABILITY_CATEGORIES.get(category)
    if not cat_info:
        return CapabilityResult(category, 0.0, 0, 0, {}, [{"error": "Unknown category"}])
    
    all_results = []
    all_details = []
    metrics = {}
    
    for suite_name in cat_info["suites"]:
        if suite_name == "HELDOUT":
            # Handled separately
            continue
        
        try:
            suite_result = run_suite(suite_name, predict, model_id, checkpoint, inference)
            all_results.append(suite_result)
            all_details.extend(suite_result["results"])
        except Exception as e:
            all_details.append({"suite": suite_name, "error": str(e)})
    
    # Compute metrics
    if all_results:
        total_examples = sum(r["n"] for r in all_results)
        total_passed = sum(r["passed"] for r in all_results)
        scores = [r["mean"] for r in all_results]
        metrics["mean_score"] = sum(scores) / len(scores)
        metrics["pass_rate"] = total_passed / total_examples if total_examples > 0 else 0
        metrics["invalid_rate"] = sum(r["invalid"] for r in all_results) / total_examples
    else:
        total_examples = 0
        total_passed = 0
        metrics = {"mean_score": 0.0, "pass_rate": 0.0, "invalid_rate": 1.0}
    
    return CapabilityResult(
        category=category,
        score=metrics.get("mean_score", 0.0),
        num_examples=total_examples,
        passed=total_passed,
        metrics=metrics,
        details=all_details
    )


def evaluate_structured_reasoning(
    predict: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str = "unknown",
    checkpoint: str = "unknown"
) -> CapabilityResult:
    """Evaluate structured reasoning format compliance."""
    # Create tasks that require structured output
    structured_tasks = [
        {"id": "struct_arith_1", "prompt": "Q: Calculate 25 * 4 using structured reasoning.\nA:", 
         "expected_tags": ["OBSERVE", "RELATE", "PLAN", "VERIFY", "ANSWER"]},
        {"id": "struct_tool_1", "prompt": "Q: Use calculator to compute 10 + 20.\nA:",
         "expected_tags": ["OBSERVE", "PLAN", "TOOL_CALL", "VERIFY", "ANSWER"]},
        {"id": "struct_arc_1", "prompt": "Q: Transform grid 010 101 010 with invert.\nA:",
         "expected_tags": ["OBSERVE", "RELATE", "PLAN", "VERIFY", "ANSWER"]},
    ]
    
    format_valid = 0
    tag_complete = 0
    verification_acc = 0
    total = len(structured_tasks)
    
    for task in structured_tasks:
        out = predict(task)
        text = out.get("text", "")
        
        is_valid, _ = validate_structured_reasoning(text)
        if is_valid:
            format_valid += 1
        
        # Check tag completeness
        sr = parse_structured_reasoning(text)
        expected = task["expected_tags"]
        present = sum(1 for tag in expected if getattr(sr, tag.lower(), None) is not None)
        if present == len(expected):
            tag_complete += 1
        
        # Check verification
        if sr.verify and "PASS" in sr.verify.upper():
            verification_acc += 1
    
    metrics = {
        "format_validity": format_valid / total,
        "tag_completeness": tag_complete / total,
        "verification_accuracy": verification_acc / total,
    }
    
    return CapabilityResult(
        category="STRUCTURED_REASONING",
        score=sum(metrics.values()) / len(metrics),
        num_examples=total,
        passed=int(sum(metrics.values()) / len(metrics) * 100),
        metrics=metrics,
        details=[{"format_validity": format_valid, "tag_completeness": tag_complete}]
    )


def evaluate_generalization(
    predict: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str = "unknown",
    checkpoint: str = "unknown"
) -> CapabilityResult:
    """Evaluate on held-out generalization cases."""
    cases = generate_all_heldout(seed=42, cases_per_type=10)
    
    def model_fn(prompt: str) -> str:
        out = predict({"prompt": prompt})
        return out.get("text", "")
    
    results, summary = evaluate_generalization(cases, model_fn, reasoning_format_available=True)
    
    metrics = {
        "exact_match_rate": summary.get("exact_match_rate", 0.0),
        "partial_match_rate": summary.get("partial_match_rate", 0.0),
        "structured_valid_rate": summary.get("structured_valid_rate", 0.0),
        "verification_passed_rate": summary.get("verification_passed_rate", 0.0),
    }
    
    # Add per-type breakdown
    for gtype, stats in summary.get("by_generalization_type", {}).items():
        metrics[f"type_{gtype}_exact"] = stats.get("exact_match_rate", 0.0)
    
    return CapabilityResult(
        category="GENERALIZATION",
        score=summary.get("exact_match_rate", 0.0),
        num_examples=summary.get("total_cases", 0),
        passed=int(summary.get("exact_match_rate", 0.0) * summary.get("total_cases", 0)),
        metrics=metrics,
        details=[{"summary": summary}]
    )


def build_capability_matrix(
    predict: Callable[[Dict[str, Any]], Dict[str, Any]],
    model_id: str = "unknown",
    checkpoint: str = "unknown",
    inference: Dict[str, Any] | None = None
) -> CapabilityMatrix:
    """Build complete capability matrix for a model."""
    from datetime import datetime
    
    categories = {}
    
    # Core capabilities
    for category in ["LANGUAGE", "ARITHMETIC", "SYMBOLIC_REASONING", 
                     "CODE", "PLANNING", "TOOL_USE", "VERIFICATION", "CORRECTION", "ARC_REASONING"]:
        categories[category] = evaluate_capability_category(category, predict, model_id, checkpoint, inference)
    
    # Structured reasoning
    categories["STRUCTURED_REASONING"] = evaluate_structured_reasoning(predict, model_id, checkpoint)
    
    # Generalization
    categories["GENERALIZATION"] = evaluate_generalization(predict, model_id, checkpoint)
    
    # Overall score (weighted average)
    weights = {
        "LANGUAGE": 0.1,
        "ARITHMETIC": 0.15,
        "SYMBOLIC_REASONING": 0.1,
        "STRUCTURED_REASONING": 0.15,
        "CODE": 0.1,
        "PLANNING": 0.05,
        "TOOL_USE": 0.1,
        "VERIFICATION": 0.1,
        "CORRECTION": 0.05,
        "ARC_REASONING": 0.05,
        "GENERALIZATION": 0.05,
    }
    
    overall = sum(categories[cat].score * w for cat, w in weights.items() if cat in categories)
    
    # Generalization gap (in-domain vs held-out)
    in_domain = sum(categories[cat].score * w for cat, w in weights.items() 
                    if cat in categories and cat != "GENERALIZATION")
    gen_score = categories.get("GENERALIZATION", CapabilityResult("GEN", 0, 0, 0, {})).score
    gen_gap = in_domain - gen_score if in_domain > 0 else 0.0
    
    from datetime import datetime
    return CapabilityMatrix(
        model_id=model_id,
        checkpoint=checkpoint,
        timestamp=datetime.utcnow().isoformat(),
        categories=categories,
        overall_score=overall,
        generalization_gap=gen_gap
    )


def save_capability_matrix(matrix: CapabilityMatrix, path: str) -> None:
    """Save capability matrix to JSON."""
    Path(path).write_text(json.dumps(matrix.to_dict(), indent=1))


def load_capability_matrix(path: str) -> CapabilityMatrix:
    """Load capability matrix from JSON."""
    data = json.loads(Path(path).read_text())
    categories = {k: CapabilityResult(**v) for k, v in data["categories"].items()}
    return CapabilityMatrix(
        model_id=data["model_id"],
        checkpoint=data["checkpoint"],
        timestamp=data["timestamp"],
        categories=categories,
        overall_score=data["overall_score"],
        generalization_gap=data["generalization_gap"]
    )


def run_capability_matrix_evaluation(
    model, tokenizer, 
    model_id: str = "hercule-lm",
    checkpoint: str = "latest",
    max_new_tokens: int = 128,
    temperature: float = 0.0
) -> CapabilityMatrix:
    """Run full capability matrix evaluation on a model."""
    predict = model_predict_factory(model, tokenizer, max_new_tokens, temperature)
    return build_capability_matrix(predict, model_id, checkpoint)


if __name__ == "__main__":
    print("N9-CAP Capability Matrix module loaded")
    print("Categories:", list(CAPABILITY_CATEGORIES.keys()))