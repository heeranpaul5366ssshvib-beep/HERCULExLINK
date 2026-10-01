from __future__ import annotations
"""Synthetic Reasoning Data Generator (N9-CAP).

Procedural generation of training examples with structured metadata.
Each sample includes: problem, target, difficulty, domain, generation_seed,
ground_truth_operation, expected_output.

Deterministic regeneration via seed.
"""

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Import structured reasoning format
try:
    from .reasoning_format import (
        StructuredReasoning, parse_structured_reasoning, serialize_structured_reasoning,
        validate_structured_reasoning,
        make_arithmetic_reasoning, make_comparison_reasoning, make_tool_call_reasoning,
        make_correction_reasoning, make_arc_reasoning
    )
    STRUCTURED_REASONING_AVAILABLE = True
except ImportError:
    STRUCTURED_REASONING_AVAILABLE = False


@dataclass
class ReasoningExample:
    """A single synthetic reasoning example with full metadata."""
    problem: str
    target: str
    difficulty: int              # 1-5
    domain: str                  # arithmetic, logic, sequence, grid, code, tool, verification
    generation_seed: int
    ground_truth_operation: str  # e.g., "add", "mul", "invert_grid", "call_calculator"
    expected_output: str
    metadata: Dict[str, Any]     # additional domain-specific info

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert numpy types to native Python
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
        return convert(d)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningExample":
        return cls(**data)


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


# --------------------------------------------------
# STAGE A: ARITHMETIC
def generate_arithmetic(seed: int, difficulty: int = 1, 
                         structured: bool = False) -> List[ReasoningExample]:
    """Generate arithmetic problems.
    
    Difficulty 1: single-digit +-
    Difficulty 2: double-digit +-
    Difficulty 3: triple-digit +-, single-digit *
    Difficulty 4: triple-digit *, division
    Difficulty 5: multi-step, mixed ops
    """
    rng = _rng(seed)
    examples = []
    
    for i in range(100):
        if difficulty == 1:
            a, b = rng.integers(1, 10, 2)
            ops = ['+', '-']
        elif difficulty == 2:
            a, b = rng.integers(1, 100, 2)
            ops = ['+', '-']
        elif difficulty == 3:
            a, b = rng.integers(1, 1000, 2)
            ops = ['+', '-', '*']
        elif difficulty == 4:
            a = rng.integers(1, 1000)
            b = rng.integers(1, 100)
            ops = ['*', '/']
        else:
            a, b, c = rng.integers(1, 100, 3)
            ops = ['+', '-', '*']
        
        op = rng.choice(ops)
        if op == '+':
            ans = a + b
            gt = "add"
        elif op == '-':
            ans = a - b
            gt = "sub"
        elif op == '*':
            ans = a * b
            gt = "mul"
        else:  # division - ensure clean division
            ans = rng.integers(1, 10)
            a = ans * b
            gt = "div"
        
        if difficulty == 5:
            # Multi-step: (a op b) op c
            op2 = rng.choice(['+', '-', '*'])
            if op2 == '+':
                ans = ans + c
            elif op2 == '-':
                ans = ans - c
            else:
                ans = ans * c
            problem = f"Calculate ({a} {op} {b}) {op2} {c}."
            gt = f"{gt}_then_{op2}"
        else:
            problem = f"Calculate {a} {op} {b}."
        
        if structured and STRUCTURED_REASONING_AVAILABLE:
            sr = make_arithmetic_reasoning(a, b, op, ans, show_work=(difficulty >= 2))
            target = serialize_structured_reasoning(sr)
        else:
            target = str(ans)
        
        examples.append(ReasoningExample(
            problem=f"Q: {problem}\nA:",
            target=target,
            difficulty=difficulty,
            domain="arithmetic",
            generation_seed=seed + i,
            ground_truth_operation=gt,
            expected_output=str(ans) + ".",
            metadata={"operands": [a, b] if difficulty < 5 else [a, b, c], "operator": op, "structured": structured}
        ))
    return examples


# --------------------------------------------------
# STAGE B: LOGIC & COMPARISON
def generate_comparison(seed: int, difficulty: int = 1,
                         structured: bool = False) -> List[ReasoningExample]:
    """Generate comparison and logic problems."""
    rng = _rng(seed)
    examples = []
    
    for i in range(50):
        if difficulty <= 2:
            a, b = rng.integers(1, 100, 2)
            ops = ['>', '<', '==', '!=']
        else:
            a, b = rng.integers(-1000, 1000, 2)
            ops = ['>', '<', '>=', '<=', '==', '!=']
        
        op = rng.choice(ops)
        if op == '>':
            ans = a > b
            gt = "gt"
        elif op == '<':
            ans = a < b
            gt = "lt"
        elif op == '>=':
            ans = a >= b
            gt = "gte"
        elif op == '<=':
            ans = a <= b
            gt = "lte"
        elif op == '==':
            ans = a == b
            gt = "eq"
        else:
            ans = a != b
            gt = "neq"
        
        if structured and STRUCTURED_REASONING_AVAILABLE:
            sr = make_comparison_reasoning(a, b, op, ans)
            target = serialize_structured_reasoning(sr)
        else:
            target = "Yes." if ans else "No."
        
        examples.append(ReasoningExample(
            problem=f"Q: Is {a} {op} {b}?\nA:",
            target=target,
            difficulty=difficulty,
            domain="comparison",
            generation_seed=seed + i,
            ground_truth_operation=gt,
            expected_output=("Yes." if ans else "No."),
            metadata={"a": int(a), "b": int(b), "operator": op, "structured": structured}
        ))
    return examples


def generate_sequence(seed: int, difficulty: int = 1) -> List[ReasoningExample]:
    """Generate sequence induction problems."""
    rng = _rng(seed)
    examples = []
    
    for i in range(50):
        if difficulty == 1:
            # Arithmetic sequence
            start = rng.integers(1, 20)
            step = rng.integers(1, 10)
            seq = [start + step * j for j in range(5)]
            next_val = seq[-1] + step
            gt = "arithmetic_seq"
        elif difficulty == 2:
            # Geometric sequence
            start = rng.integers(1, 10)
            ratio = rng.integers(2, 4)
            seq = [start * (ratio ** j) for j in range(5)]
            next_val = seq[-1] * ratio
            gt = "geometric_seq"
        elif difficulty == 3:
            # Fibonacci-like
            a, b = rng.integers(1, 10, 2)
            seq = [a, b]
            for _ in range(3):
                seq.append(seq[-1] + seq[-2])
            next_val = seq[-1] + seq[-2]
            gt = "fibonacci_seq"
        else:
            # Alternating pattern
            start = rng.integers(1, 20)
            step1 = rng.integers(1, 5)
            step2 = rng.integers(1, 5)
            seq = []
            for j in range(5):
                if j % 2 == 0:
                    seq.append(start + (j//2) * step1)
                else:
                    seq.append(start + (j//2) * step2 + step1)
            # Next follows pattern
            next_val = start + 3 * step1 if len(seq) % 2 == 0 else start + 2 * step2 + 2 * step1
            gt = "alternating_seq"
        
        examples.append(ReasoningExample(
            problem=f"Q: Continue: {', '.join(map(str, seq))}, ?\nA:",
            target=str(next_val),
            difficulty=difficulty,
            domain="sequence",
            generation_seed=seed + i,
            ground_truth_operation=gt,
            expected_output=str(next_val) + ".",
            metadata={"sequence": seq, "type": gt}
        ))
    return examples


# --------------------------------------------------
# STAGE B: SYMBOLIC TRANSFORMATION
def generate_symbolic_transform(seed: int, difficulty: int = 1) -> List[ReasoningExample]:
    """Generate string/list transformation problems."""
    rng = _rng(seed)
    examples = []
    
    transforms = [
        ("reverse", lambda s: s[::-1]),
        ("uppercase", lambda s: s.upper()),
        ("lowercase", lambda s: s.lower()),
        ("duplicate", lambda s: s + s),
        ("first_half", lambda s: s[:len(s)//2]),
        ("remove_vowels", lambda s: ''.join(c for c in s if c.lower() not in 'aeiou')),
    ]
    
    words = ["hello", "world", "python", "reasoning", "transform", "pattern", "sequence", "logic"]
    
    for i in range(50):
        name, fn = rng.choice(transforms)
        word = rng.choice(words)
        if difficulty >= 3:
            word = word + rng.choice(["_test", "_data", "_example"])
        
        result = fn(word)
        examples.append(ReasoningExample(
            problem=f"Q: Apply {name} to '{word}'.\nA:",
            target=result,
            difficulty=difficulty,
            domain="symbolic_transform",
            generation_seed=seed + i,
            ground_truth_operation=name,
            expected_output=result + ".",
            metadata={"input": word, "transform": name}
        ))
    return examples


# --------------------------------------------------
# STAGE C: CODE
def generate_code(seed: int, difficulty: int = 1) -> List[ReasoningExample]:
    """Generate simple code generation/completion problems."""
    rng = _rng(seed)
    examples = []
    
    templates = [
        # Function definition
        ('def add_{n}(x):\n    return x + {n}', 'def add_{n}(x):\n    return x + {n}'),
        ('def mul_{n}(x):\n    return x * {n}', 'def mul_{n}(x):\n    return x * {n}'),
        ('def is_even(x):\n    return x % 2 == 0', 'def is_even(x):\n    return x % 2 == 0'),
        ('def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)', 
         'def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n-1)'),
        # Loop
        ('for i in range({n}):\n    print(i)', 'for i in range({n}):\n    print(i)'),
        # List comprehension
        ('[x*2 for x in range({n})]', '[x*2 for x in range({n})]'),
    ]
    
    for i in range(50):
        template, target_template = rng.choice(templates)
        n = rng.integers(1, 10)
        if difficulty == 1:
            prompt = f"Q: Write python: {template.format(n=n)}"
            target = target_template.format(n=n)
        elif difficulty == 2:
            # Completion
            prompt = f"Q: Complete: {template.format(n=n)[:-10]}"
            target = template.format(n=n)
        else:
            # With docstring
            prompt = f"Q: Write python function that {template.format(n=n).split('(')[0][4:]}"
            target = template.format(n=n)
        
        examples.append(ReasoningExample(
            problem=f"{prompt}\nA:",
            target=target,
            difficulty=difficulty,
            domain="code",
            generation_seed=seed + i,
            ground_truth_operation="code_gen",
            expected_output=target,
            metadata={"template": template, "n": int(n)}
        ))
    return examples


# --------------------------------------------------
# STAGE D: TOOL USE
def generate_tool_use(seed: int, difficulty: int = 1,
                       structured: bool = False) -> List[ReasoningExample]:
    """Generate tool call examples with structured reasoning."""
    rng = _rng(seed)
    examples = []
    
    def to_native(obj):
        """Convert numpy types to native Python types."""
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: to_native(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [to_native(v) for v in obj]
        return obj
    
    # Additional tool types for structured reasoning
    tool_scenarios = [
        # Calculator with full reasoning
        lambda: ("calculator", "compute", int(rng.integers(1, 1000)), int(rng.integers(1, 1000)), 
                 rng.choice(['+', '-', '*', '/'])),
        # Search
        lambda: ("search", "search", rng.choice(["python tutorial", "transformer architecture", 
                                                   "BPE tokenizer", "RMSNorm vs LayerNorm", 
                                                   "RoPE positional encoding"])),
        # File read
        lambda: ("file_read", "read", rng.choice(["/data/train.txt", "/config/model.json", 
                                                   "/tmp/output.log", "/models/checkpoint.npz"])),
        # File write
        lambda: ("file_write", "write", rng.choice(["/tmp/result.txt", "/data/output.json"]), 
                 rng.choice(["done", "success", "error", "completed"])),
        # JSON validation
        lambda: ("json_validator", "validate", json.dumps({
            "model": "hercule-lm", "params": int(rng.integers(1000000, 100000000))
        })),
    ]
    
    for i in range(50):
        # Generate a tool scenario
        tool_name, op, *params = rng.choice(tool_scenarios)()
        
        if tool_name == "calculator":
            a, b, op_sym = params
            a, b = int(a), int(b)
            if op_sym == '+':
                result = a + b
            elif op_sym == '-':
                result = a - b
            elif op_sym == '*':
                result = a * b
            else:
                result = a // b if b != 0 else 0
            args = {"expression": f"{a} {op_sym} {b}"}
            problem = f"Q: Calculate {a} {op_sym} {b} using calculator.\nA:"
            gt = f"calc_{op_sym}"
        elif tool_name == "search":
            query = params[0]
            result = f"Results for: {query}"
            args = {"query": query}
            problem = f"Q: Search for information about '{query}'.\nA:"
            gt = "search"
        elif tool_name == "file_read":
            path = params[0]
            result = f"Content of {path}"
            args = {"path": path}
            problem = f"Q: Read the file at {path}.\nA:"
            gt = "file_read"
        elif tool_name == "file_write":
            path, content = params
            result = f"Written to {path}"
            args = {"path": path, "content": content}
            problem = f"Q: Write '{content}' to {path}.\nA:"
            gt = "file_write"
        elif tool_name == "json_validator":
            json_str = params[0]
            result = "Valid JSON"
            args = {"json": json.loads(json_str)}
            problem = f"Q: Validate this JSON: {json_str}\nA:"
            gt = "json_validate"
        else:
            continue
        
        # Convert all to native types
        args = to_native(args)
        result = to_native(result)
        
        if structured and STRUCTURED_REASONING_AVAILABLE:
            sr = make_tool_call_reasoning(tool_name, args, result, verified=True)
            target = serialize_structured_reasoning(sr)
        else:
            target = f'<TOOL_CALL>{json.dumps({"tool": tool_name, "arguments": args})}</TOOL_CALL>'
        
        examples.append(ReasoningExample(
            problem=problem,
            target=target,
            difficulty=difficulty,
            domain="tool_use",
            generation_seed=seed + i,
            ground_truth_operation=gt,
            expected_output=target if structured else f'Tool {tool_name} returned: {result}',
            metadata={"tool": tool_name, "operation": op, "args": args, "result": str(result), "structured": structured}
        ))
    return examples


# --------------------------------------------------
# STAGE D: VERIFICATION & CORRECTION
def generate_verification(seed: int, difficulty: int = 1,
                           structured: bool = False) -> List[ReasoningExample]:
    """Generate verification and correction examples with structured reasoning."""
    rng = _rng(seed)
    examples = []
    
    # Error types for arithmetic
    arithmetic_errors = ['off_by_one', 'wrong_op', 'sign_error', 'overflow']
    
    # Error types for tool calls
    tool_errors = ['malformed_json', 'invalid_tool', 'missing_args', 'permission_denied']
    
    # Error types for ARC
    arc_errors = ['wrong_transform', 'wrong_color', 'wrong_dimensions', 'incomplete_grid']
    
    for i in range(50):
        scenario = rng.choice(['arithmetic', 'tool_call', 'arc_grid', 'code'])
        
        if scenario == 'arithmetic':
            a, b = rng.integers(1, 100, 2)
            op = rng.choice(['+', '-', '*'])
            if op == '+':
                correct = a + b
            elif op == '-':
                correct = a - b
            else:
                correct = a * b
            
            error_type = rng.choice(arithmetic_errors)
            if error_type == 'off_by_one':
                wrong = correct + rng.choice([-1, 1])
            elif error_type == 'wrong_op':
                wrong_op = rng.choice([o for o in ['+', '-', '*'] if o != op])
                if wrong_op == '+':
                    wrong = a + b
                elif wrong_op == '-':
                    wrong = a - b
                else:
                    wrong = a * b
            elif error_type == 'sign_error':
                wrong = -correct
            else:  # overflow
                wrong = correct * 1000
            
            problem_base = f"{a} {op} {b} = {wrong}"
            gt = f"verify_{error_type}"
            
        elif scenario == 'tool_call':
            tool = rng.choice(["calculator", "search", "file_read", "file_write"])
            error_type = rng.choice(tool_errors)
            
            if error_type == 'malformed_json':
                problem_base = f'<TOOL_CALL>{{"tool": "{tool}", "arguments": {{missing_brace}}</TOOL_CALL>'
                wrong = "malformed"
            elif error_type == 'invalid_tool':
                problem_base = f'<TOOL_CALL>{{"tool": "invalid_tool", "arguments": {{}}}}</TOOL_CALL>'
                wrong = "invalid_tool"
            elif error_type == 'missing_args':
                problem_base = f'<TOOL_CALL>{{"tool": "{tool}", "arguments": {{}}}}</TOOL_CALL>'
                wrong = "missing_args"
            else:  # permission_denied
                problem_base = f'<TOOL_CALL>{{"tool": "delete_all", "arguments": {{}}}}</TOOL_CALL>'
                wrong = "permission_denied"
            
            correct = f"Valid {tool} call with proper arguments"
            gt = f"verify_tool_{error_type}"
            
        elif scenario == 'arc_grid':
            # Generate a grid and wrong transformation
            h, w = rng.integers(3, 5, 2)
            grid = [[rng.integers(0, 2) for _ in range(w)] for _ in range(h)]
            error_type = rng.choice(arc_errors)
            wrong = "incorrect_transform"
            correct = "correct_transform"
            problem_base = f"Grid {grid} -> {wrong}"
            gt = f"verify_arc_{error_type}"
            
        else:  # code
            error_type = rng.choice(['syntax_error', 'logic_error', 'type_error'])
            problem_base = f"Code with {error_type}"
            wrong = "buggy_code"
            correct = "fixed_code"
            gt = f"verify_code_{error_type}"
        
        if difficulty == 1:
            # Simple verification
            problem = f"Q: Verify: {problem_base}\nA:"
            if structured and STRUCTURED_REASONING_AVAILABLE:
                sr = make_correction_reasoning(problem_base, wrong, correct, error_type)
                target = serialize_structured_reasoning(sr)
                expected = f"VERIFICATION FAILED. {problem_base}. CORRECTION: {correct}."
            else:
                target = f"INCORRECT. {problem_base}. CORRECTION: {correct}."
                expected = target
        elif difficulty == 2:
            # Correction
            problem = f"Q: Correct if wrong: {problem_base}\nA:"
            if structured and STRUCTURED_REASONING_AVAILABLE:
                sr = make_correction_reasoning(problem_base, wrong, correct, error_type)
                target = serialize_structured_reasoning(sr)
            else:
                target = f"CORRECTION: {correct}."
            expected = target
        else:
            # Verification with explanation
            problem = f"Q: Check and explain: {problem_base}\nA:"
            if structured and STRUCTURED_REASONING_AVAILABLE:
                sr = make_correction_reasoning(problem_base, wrong, correct, error_type)
                target = serialize_structured_reasoning(sr)
            else:
                target = f"VERIFICATION FAILED. {problem_base} is incorrect. The correct answer is {correct}. Error: {error_type}."
            expected = target
        
        examples.append(ReasoningExample(
            problem=problem,
            target=target,
            difficulty=difficulty,
            domain="verification",
            generation_seed=seed + i,
            ground_truth_operation=gt,
            expected_output=expected,
            metadata={"scenario": scenario, "error_type": error_type, 
                      "correct": str(correct), "wrong": str(wrong), "structured": structured}
        ))
    return examples


# --------------------------------------------------
# STAGE E: ARC GRID REASONING
def generate_arc_grid(seed: int, difficulty: int = 1,
                       structured: bool = False) -> List[ReasoningExample]:
    """Generate ARC-style grid transformation problems with structured reasoning."""
    rng = _rng(seed)
    examples = []
    
    def make_grid(h, w, fill=0):
        return [[fill for _ in range(w)] for _ in range(h)]
    
    transforms = [
        # Invert colors (0<->1 for binary)
        ("invert", lambda g: [[1-v for v in row] for row in g]),
        # Rotate 90
        ("rot90", lambda g: list(zip(*g[::-1]))),
        # Rotate 180
        ("rot180", lambda g: [row[::-1] for row in g[::-1]]),
        # Flip horizontal
        ("flip_h", lambda g: [row[::-1] for row in g]),
        # Flip vertical
        ("flip_v", lambda g: g[::-1]),
        # Transpose
        ("transpose", lambda g: list(zip(*g))),
    ]
    
    for i in range(50):
        h = rng.integers(3, 6)
        w = rng.integers(3, 6)
        
        if difficulty == 1:
            # Binary grid
            grid = [[rng.integers(0, 2) for _ in range(w)] for _ in range(h)]
            colors = 2
        elif difficulty == 2:
            # 3 colors
            grid = [[rng.integers(0, 3) for _ in range(w)] for _ in range(h)]
            colors = 3
        else:
            # More colors, larger
            grid = [[rng.integers(0, 5) for _ in range(w)] for _ in range(h)]
            colors = 5
        
        name, fn = rng.choice(transforms)
        try:
            result = fn(grid)
            # Convert tuples back to lists
            result = [list(row) for row in result]
        except Exception:
            continue
        
        # Format as compact string
        grid_str = ' '.join(''.join(str(v) for v in row) for row in grid)
        result_str = ' '.join(''.join(str(v) for v in row) for row in result)
        
        if structured and STRUCTURED_REASONING_AVAILABLE:
            sr = make_arc_reasoning(grid, result, name)
            target = serialize_structured_reasoning(sr)
        else:
            target = result_str
        
        examples.append(ReasoningExample(
            problem=f"Q: Transform grid: {grid_str}\nA:",
            target=target,
            difficulty=difficulty,
            domain="arc_grid",
            generation_seed=seed + i,
            ground_truth_operation=name,
            expected_output=result_str,
            metadata={"input_grid": grid, "output_grid": result, "transform": name, "colors": colors, "structured": structured}
        ))
    return examples


# --------------------------------------------------
# MASTER GENERATOR
def generate_curriculum(
    seed: int = 0,
    stage_a_weight: float = 0.3,
    stage_b_weight: float = 0.2,
    stage_c_weight: float = 0.2,
    stage_d_weight: float = 0.15,
    stage_e_weight: float = 0.15,
    difficulties: Tuple[int, ...] = (1, 2, 3),
    examples_per_difficulty: int = 50,
    structured: bool = False
) -> List[ReasoningExample]:
    """Generate a full curriculum mixing all stages."""
    all_examples = []
    
    # Stage A: Language + Arithmetic
    for d in difficulties:
        n = int(examples_per_difficulty * stage_a_weight)
        all_examples.extend(generate_arithmetic(seed + 1000*d, d, structured)[:n])
        all_examples.extend(generate_comparison(seed + 2000*d, d, structured)[:n//2])
        all_examples.extend(generate_sequence(seed + 3000*d, d)[:n//2])
    
    # Stage B: Structured Reasoning
    for d in difficulties:
        n = int(examples_per_difficulty * stage_b_weight)
        all_examples.extend(generate_symbolic_transform(seed + 4000*d, d)[:n])
    
    # Stage C: Code
    for d in difficulties:
        n = int(examples_per_difficulty * stage_c_weight)
        all_examples.extend(generate_code(seed + 5000*d, d)[:n])
    
    # Stage D: Tool Use + Verification
    for d in difficulties:
        n = int(examples_per_difficulty * stage_d_weight)
        all_examples.extend(generate_tool_use(seed + 6000*d, d, structured)[:n//2])
        all_examples.extend(generate_verification(seed + 7000*d, d, structured)[:n//2])
    
    # Stage E: ARC
    for d in difficulties:
        n = int(examples_per_difficulty * stage_e_weight)
        all_examples.extend(generate_arc_grid(seed + 8000*d, d, structured)[:n])
    
    # Shuffle deterministically
    rng = _rng(seed + 99999)
    rng.shuffle(all_examples)
    
    return all_examples


def save_curriculum(examples: List[ReasoningExample], path: str) -> None:
    """Save curriculum to JSONL file."""
    with open(path, 'w') as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict()) + '\n')


def load_curriculum(path: str) -> List[ReasoningExample]:
    """Load curriculum from JSONL file."""
    examples = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                examples.append(ReasoningExample.from_dict(json.loads(line)))
    return examples


def curriculum_stats(examples: List[ReasoningExample]) -> Dict[str, Any]:
    """Compute statistics on a curriculum."""
    domains = {}
    difficulties = {}
    for ex in examples:
        domains[ex.domain] = domains.get(ex.domain, 0) + 1
        difficulties[ex.difficulty] = difficulties.get(ex.difficulty, 0) + 1
    
    return {
        "total_examples": len(examples),
        "by_domain": domains,
        "by_difficulty": difficulties,
        "avg_problem_len": np.mean([len(e.problem) for e in examples]),
        "avg_target_len": np.mean([len(e.target) for e in examples]),
    }


if __name__ == "__main__":
    # Demo
    curriculum = generate_curriculum(seed=42, examples_per_difficulty=20)
    print(f"Generated {len(curriculum)} examples")
    stats = curriculum_stats(curriculum)
    print(json.dumps(stats, indent=1))
    
    # Save sample
    save_curriculum(curriculum[:10], "/tmp/sample_curriculum.jsonl")
    print("Saved sample to /tmp/sample_curriculum.jsonl")