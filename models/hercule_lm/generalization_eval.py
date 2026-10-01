from __future__ import annotations
"""Held-Out Generalization Evaluation Framework (N9-CAP §5).

Evaluates model on distributions that differ from training:
- unseen numbers, positions, colors, grid dimensions
- reordered objects, distractors
- unseen transformation compositions
- longer reasoning sequences
- unseen combinations of known primitives
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Set

import numpy as np

from .synthetic_reasoning import (
    ReasoningExample, generate_arithmetic, generate_comparison, generate_sequence,
    generate_tool_use, generate_verification, generate_arc_grid
)
from .reasoning_format import (
    StructuredReasoning, parse_structured_reasoning, serialize_structured_reasoning,
    validate_structured_reasoning
)


@dataclass
class GeneralizationTestCase:
    """A single held-out test case."""
    problem: str
    target: str
    domain: str
    difficulty: int
    generalization_type: str  # e.g., "unseen_numbers", "composition"
    metadata: Dict[str, Any] = field(default_factory=dict)
    structured: bool = False


@dataclass
class GeneralizationResult:
    """Result of generalization evaluation."""
    test_case: GeneralizationTestCase
    model_output: str
    parsed_reasoning: Optional[StructuredReasoning]
    exact_match: bool
    partial_match: bool
    structured_valid: bool
    verification_passed: bool
    latency_ms: float


# --------------------------------------------------
# Held-out data generators

def generate_unseen_numbers(seed: int, count: int = 100, 
                            train_range: Tuple[int, int] = (1, 1000)) -> List[GeneralizationTestCase]:
    """Generate arithmetic with numbers outside training range."""
    rng = np.random.default_rng(seed)
    cases = []
    
    # Test ranges: negative, very large, decimals (if supported)
    test_ranges = [
        (-10000, -1001),      # negative
        (1001, 10000),        # larger than train
        (100000, 1000000),    # much larger
    ]
    
    for i in range(count):
        range_idx = i % len(test_ranges)
        low, high = test_ranges[range_idx]
        a, b = rng.integers(low, high, 2)
        op = rng.choice(['+', '-', '*'])
        
        if op == '+':
            ans = a + b
        elif op == '-':
            ans = a - b
        else:
            ans = a * b
        
        cases.append(GeneralizationTestCase(
            problem=f"Q: Calculate {a} {op} {b}.\nA:",
            target=str(ans),
            domain="arithmetic",
            difficulty=2,
            generalization_type="unseen_numbers",
            metadata={"a": int(a), "b": int(b), "operator": op, "range": f"[{low},{high}]"}
        ))
    
    return cases


def generate_unseen_grid_properties(seed: int, count: int = 50) -> List[GeneralizationTestCase]:
    """Generate ARC grids with unseen colors, sizes, positions."""
    rng = np.random.default_rng(seed)
    cases = []
    
    transforms = [
        ("invert", lambda g: [[1-v for v in row] for row in g]),
        ("rot90", lambda g: list(zip(*g[::-1]))),
        ("rot180", lambda g: [row[::-1] for row in g[::-1]]),
        ("flip_h", lambda g: [row[::-1] for row in g]),
        ("flip_v", lambda g: g[::-1]),
        ("transpose", lambda g: list(zip(*g))),
    ]
    
    for i in range(count):
        # Unseen grid sizes (larger than training 3-5)
        h = rng.integers(6, 10)
        w = rng.integers(6, 10)
        
        # Unseen colors (training: 0-4, test: 5-9)
        grid = [[rng.integers(5, 10) for _ in range(w)] for _ in range(h)]
        
        name, fn = rng.choice(transforms)
        try:
            result = fn(grid)
            result = [list(row) for row in result]
        except Exception:
            continue
        
        grid_str = ' '.join(''.join(str(v) for v in row) for row in grid)
        result_str = ' '.join(''.join(str(v) for v in row) for row in result)
        
        cases.append(GeneralizationTestCase(
            problem=f"Q: Transform grid: {grid_str}\nA:",
            target=result_str,
            domain="arc_grid",
            difficulty=3,
            generalization_type="unseen_grid_properties",
            metadata={"transform": name, "grid_size": f"{h}x{w}", "colors": "5-9"}
        ))
    
    return cases


def generate_compositional_generalization(seed: int, count: int = 50) -> List[GeneralizationTestCase]:
    """Generate compositional tasks (combine known transforms)."""
    rng = np.random.default_rng(seed)
    cases = []
    
    # Training has single transforms; test has compositions
    transforms = [
        ("invert", lambda g: [[1-v for v in row] for row in g]),
        ("rot90", lambda g: list(zip(*g[::-1]))),
        ("rot180", lambda g: [row[::-1] for row in g[::-1]]),
        ("flip_h", lambda g: [row[::-1] for row in g]),
        ("flip_v", lambda g: g[::-1]),
        ("transpose", lambda g: list(zip(*g))),
    ]
    
    for i in range(count):
        h = rng.integers(3, 6)
        w = rng.integers(3, 6)
        grid = [[rng.integers(0, 2) for _ in range(w)] for _ in range(h)]
        
        # Compose 2 transforms
        t1_name, t1_fn = rng.choice(transforms)
        t2_name, t2_fn = rng.choice(transforms)
        
        try:
            intermediate = t1_fn(grid)
            intermediate = [list(row) for row in intermediate]
            result = t2_fn(intermediate)
            result = [list(row) for row in result]
        except Exception:
            continue
        
        grid_str = ' '.join(''.join(str(v) for v in row) for row in grid)
        result_str = ' '.join(''.join(str(v) for v in row) for row in result)
        
        cases.append(GeneralizationTestCase(
            problem=f"Q: Transform grid with {t1_name} then {t2_name}: {grid_str}\nA:",
            target=result_str,
            domain="arc_grid",
            difficulty=4,
            generalization_type="compositional",
            metadata={"transforms": [t1_name, t2_name]}
        ))
    
    return cases


def generate_reordered_objects(seed: int, count: int = 50) -> List[GeneralizationTestCase]:
    """Generate tasks with reordered objects/operands."""
    rng = np.random.default_rng(seed)
    cases = []
    
    for i in range(count):
        a, b = rng.integers(1, 1000, 2)
        op = rng.choice(['+', '-', '*', '/'])
        
        if op == '+':
            ans = a + b
            # Test commutativity: b + a
            problem = f"Q: Calculate {b} + {a}.\nA:"
        elif op == '*':
            ans = a * b
            problem = f"Q: Calculate {b} * {a}.\nA:"
        elif op == '-':
            ans = a - b
            # Test non-commutativity awareness
            problem = f"Q: Calculate {b} - {a}.\nA:"
            ans = b - a
        else:  # division
            if b != 0:
                ans = a // b
                problem = f"Q: Calculate {b} / {a}.\nA:"
                ans = b // a if a != 0 else 0
            else:
                continue
        
        cases.append(GeneralizationTestCase(
            problem=problem,
            target=str(ans),
            domain="arithmetic",
            difficulty=2,
            generalization_type="reordered_objects",
            metadata={"original": f"{a} {op} {b}", "commutative": op in ['+', '*']}
        ))
    
    return cases


def generate_distractor_objects(seed: int, count: int = 50) -> List[GeneralizationTestCase]:
    """Generate tasks with irrelevant distractor information."""
    rng = np.random.default_rng(seed)
    cases = []
    
    distractors = [
        "The weather today is sunny.",
        "Remember to bring an umbrella.",
        "The cat sat on the mat.",
        "Paris is the capital of France.",
        "2 + 2 = 4.",
    ]
    
    for i in range(count):
        a, b = rng.integers(1, 100, 2)
        op = rng.choice(['+', '-', '*'])
        
        if op == '+':
            ans = a + b
        elif op == '-':
            ans = a - b
        else:
            ans = a * b
        
        distractor = rng.choice(distractors)
        problem = f"Q: {distractor} Calculate {a} {op} {b}.\nA:"
        
        cases.append(GeneralizationTestCase(
            problem=problem,
            target=str(ans),
            domain="arithmetic",
            difficulty=2,
            generalization_type="distractors",
            metadata={"distractor": distractor}
        ))
    
    return cases


def generate_longer_sequences(seed: int, count: int = 50) -> List[GeneralizationTestCase]:
    """Generate longer reasoning sequences than training."""
    rng = np.random.default_rng(seed)
    cases = []
    
    for i in range(count):
        # Multi-step arithmetic chain
        steps = rng.integers(4, 8)  # Training: 1-3 steps
        vals = [rng.integers(1, 20)]
        ops = []
        
        for _ in range(steps):
            op = rng.choice(['+', '-', '*'])
            val = rng.integers(1, 20)
            ops.append(op)
            if op == '+':
                vals.append(vals[-1] + val)
            elif op == '-':
                vals.append(vals[-1] - val)
            else:
                vals.append(vals[-1] * val)
        
        # Build problem
        expr = str(vals[0])
        for op, v in zip(ops, vals[1:]):
            expr += f" {op} {v}"
        
        problem = f"Q: Calculate {expr}.\nA:"
        
        cases.append(GeneralizationTestCase(
            problem=problem,
            target=str(vals[-1]),
            domain="arithmetic",
            difficulty=4,
            generalization_type="longer_sequences",
            metadata={"steps": steps, "expression": expr}
        ))
    
    return cases


def generate_unseen_tool_combinations(seed: int, count: int = 30) -> List[GeneralizationTestCase]:
    """Generate tool use with unseen tool combinations."""
    rng = np.random.default_rng(seed)
    cases = []
    
    # Training: single tool calls; Test: multi-tool chains
    for i in range(count):
        # Chain: calculator -> file_write
        a, b = rng.integers(1, 100, 2)
        op = rng.choice(['+', '-', '*'])
        if op == '+':
            calc_result = a + b
        elif op == '-':
            calc_result = a - b
        else:
            calc_result = a * b
        
        problem = f"Q: Calculate {a} {op} {b} and write the result to /tmp/out.txt.\nA:"
        
        # Expected: two tool calls
        cases.append(GeneralizationTestCase(
            problem=problem,
            target=f"Multi-step: calculator then file_write",
            domain="tool_use",
            difficulty=4,
            generalization_type="unseen_tool_combinations",
            metadata={"tools": ["calculator", "file_write"], "chain": True}
        ))
    
    return cases


# --------------------------------------------------
# Master held-out generator

def generate_all_heldout(
    seed: int = 42,
    cases_per_type: int = 50
) -> List[GeneralizationTestCase]:
    """Generate all held-out generalization test cases."""
    all_cases = []
    
    generators = [
        ("unseen_numbers", generate_unseen_numbers),
        ("unseen_grid_properties", generate_unseen_grid_properties),
        ("compositional", generate_compositional_generalization),
        ("reordered_objects", generate_reordered_objects),
        ("distractors", generate_distractor_objects),
        ("longer_sequences", generate_longer_sequences),
        ("unseen_tool_combinations", generate_unseen_tool_combinations),
    ]
    
    for i, (name, gen_fn) in enumerate(generators):
        cases = gen_fn(seed + i * 1000, cases_per_type)
        for c in cases:
            c.metadata["generalization_type"] = name
        all_cases.extend(cases)
        print(f"  {name}: {len(cases)} cases")
    
    # Shuffle
    rng = np.random.default_rng(seed + 99999)
    rng.shuffle(all_cases)
    
    return all_cases


def save_heldout(cases: List[GeneralizationTestCase], path: str) -> None:
    """Save held-out cases to JSONL."""
    with open(path, 'w') as f:
        for c in cases:
            d = asdict(c)
            # Convert numpy types
            def convert(obj):
                if isinstance(obj, (np.integer,)):
                    return int(obj)
                if isinstance(obj, (np.floating,)):
                    return float(obj)
                if isinstance(obj, np.ndarray):
                    return obj.tolist()
                if isinstance(obj, dict):
                    return {k: convert(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [convert(v) for v in obj]
                return obj
            f.write(json.dumps(convert(d)) + '\n')


def load_heldout(path: str) -> List[GeneralizationTestCase]:
    """Load held-out cases from JSONL."""
    cases = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                cases.append(GeneralizationTestCase(**data))
    return cases


# --------------------------------------------------
# Evaluation

def evaluate_generalization(
    cases: List[GeneralizationTestCase],
    model_fn: Callable[[str], str],
    tokenizer: Optional[Any] = None,
    reasoning_format_available: bool = True
) -> Tuple[List[GeneralizationResult], Dict[str, Any]]:
    """Evaluate model on held-out generalization cases.
    
    Args:
        cases: Held-out test cases
        model_fn: Function that takes prompt and returns model output
        tokenizer: Optional tokenizer for parsing structured output
        reasoning_format_available: Whether reasoning_format module is available
    
    Returns:
        List of results and summary statistics
    """
    results = []
    
    for case in cases:
        import time
        start = time.perf_counter()
        
        model_output = model_fn(case.problem)
        
        latency_ms = (time.perf_counter() - start) * 1000
        
        # Parse structured reasoning if available
        parsed_reasoning = None
        structured_valid = False
        verification_passed = False
        
        if reasoning_format_available and case.structured:
            try:
                parsed_reasoning = parse_structured_reasoning(model_output)
                is_valid, _ = validate_structured_reasoning(model_output)
                structured_valid = is_valid
                
                if parsed_reasoning.verify:
                    verification_passed = "PASS" in parsed_reasoning.verify.upper()
            except Exception:
                pass
        
        # Check exact match
        exact_match = model_output.strip() == case.target.strip()
        
        # Check partial match (answer contained)
        if case.structured and parsed_reasoning and parsed_reasoning.answer:
            partial_match = case.target.strip() in parsed_reasoning.answer or \
                           parsed_reasoning.answer.strip() in case.target.strip()
        else:
            partial_match = case.target.strip() in model_output
        
        results.append(GeneralizationResult(
            test_case=case,
            model_output=model_output,
            parsed_reasoning=parsed_reasoning,
            exact_match=exact_match,
            partial_match=partial_match,
            structured_valid=structured_valid,
            verification_passed=verification_passed,
            latency_ms=latency_ms
        ))
    
    # Summary statistics
    summary = {
        "total_cases": len(cases),
        "exact_match_rate": sum(r.exact_match for r in results) / len(results),
        "partial_match_rate": sum(r.partial_match for r in results) / len(results),
        "structured_valid_rate": sum(r.structured_valid for r in results) / len(results),
        "verification_passed_rate": sum(r.verification_passed for r in results) / len(results),
        "avg_latency_ms": np.mean([r.latency_ms for r in results]),
        "by_generalization_type": {},
        "by_domain": {},
    }
    
    # Break down by generalization type
    by_type: Dict[str, List[GeneralizationResult]] = {}
    for r in results:
        gtype = r.test_case.generalization_type
        by_type.setdefault(gtype, []).append(r)
    
    for gtype, type_results in by_type.items():
        summary["by_generalization_type"][gtype] = {
            "count": len(type_results),
            "exact_match_rate": sum(r.exact_match for r in type_results) / len(type_results),
            "partial_match_rate": sum(r.partial_match for r in type_results) / len(type_results),
        }
    
    # Break down by domain
    by_domain: Dict[str, List[GeneralizationResult]] = {}
    for r in results:
        domain = r.test_case.domain
        by_domain.setdefault(domain, []).append(r)
    
    for domain, domain_results in by_domain.items():
        summary["by_domain"][domain] = {
            "count": len(domain_results),
            "exact_match_rate": sum(r.exact_match for r in domain_results) / len(domain_results),
        }
    
    return results, summary


if __name__ == "__main__":
    # Generate held-out cases
    print("Generating held-out generalization cases...")
    cases = generate_all_heldout(seed=42, cases_per_type=20)
    print(f"Total cases: {len(cases)}")
    
    # Save
    save_heldout(cases, "/tmp/heldout_generalization.jsonl")
    print("Saved to /tmp/heldout_generalization.jsonl")
    
    # Print summary by type
    from collections import Counter
    types = Counter(c.generalization_type for c in cases)
    for t, count in types.items():
        print("  " + t + ": " + str(count))