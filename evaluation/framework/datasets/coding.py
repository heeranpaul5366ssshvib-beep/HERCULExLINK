from __future__ import annotations
"""Coding datasets checked in the isolated sandbox (Phase 5)."""

from typing import List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def coding_tasks() -> List[EvalTask]:
    """HumanEval/MBPP/LiveCodeBench-style code generation.

    Scoring: PROMPT -> HERCULE -> CODE -> SANDBOX -> TESTS -> SCORE.
    Generated code runs only in the isolated subprocess sandbox, never
    on the host directly. Sandboxed tasks require HERCULE_EVAL_SANDBOX=1.
    """
    return [
        EvalTask(
            task_id="coding-humaneval-style-001",
            suite="coding",
            category=EvalCategory.CODING,
            prompt=("Write a Python function `add_numbers(a, b)` that returns the sum "
                    "of a and b. Return only a Python code block."),
            expected_format="python code block",
            scoring_method=ScoringMethod.CODE_PASS,
            expected={"tests": [
                {"name": "positive", "expression": "add_numbers(2, 3)", "expected": "5"},
                {"name": "negative", "expression": "add_numbers(-4, 4)", "expected": "0"},
            ]},
            evaluator="sandboxed unit tests",
            difficulty="easy", timeout_s=90.0,
            required_capabilities=[], safety_class=SafetyClass.SANDBOXED,
            style="HumanEval-style",
        ),
        EvalTask(
            task_id="coding-mbpp-style-002",
            suite="coding",
            category=EvalCategory.CODING,
            prompt=("Write a Python function `is_even(n)` that returns True when n is "
                    "even, False otherwise. Return only a Python code block."),
            expected_format="python code block",
            scoring_method=ScoringMethod.CODE_PASS,
            expected={"tests": [
                {"name": "even", "expression": "is_even(10)", "expected": "True"},
                {"name": "odd", "expression": "is_even(7)", "expected": "False"},
                {"name": "zero", "expression": "is_even(0)", "expected": "True"},
            ]},
            evaluator="sandboxed unit tests",
            difficulty="easy", timeout_s=90.0,
            safety_class=SafetyClass.SANDBOXED, style="MBPP-style",
        ),
        EvalTask(
            task_id="coding-livecodebench-style-003",
            suite="coding",
            category=EvalCategory.CODING,
            prompt=("Write a Python function `second_largest(nums)` that returns the "
                    "second largest distinct value in a non-empty list of integers "
                    "(None if it does not exist). Return only a Python code block."),
            expected_format="python code block",
            scoring_method=ScoringMethod.CODE_PASS,
            expected={"tests": [
                {"name": "typical", "expression": "second_largest([1, 5, 3])", "expected": "3"},
                {"name": "duplicates", "expression": "second_largest([4, 4, 2])", "expected": "2"},
                {"name": "single", "expression": "second_largest([9])", "expected": "None"},
            ]},
            evaluator="sandboxed unit tests",
            difficulty="medium", timeout_s=120.0,
            safety_class=SafetyClass.SANDBOXED, style="LiveCodeBench-style",
        ),
        EvalTask(
            task_id="coding-swebench-style-004",
            suite="coding",
            category=EvalCategory.CODING,
            prompt=("A buggy function `median_bad(nums)` sorts a copy of the input "
                    "incorrectly: it returns nums[0] always. Write a correct Python "
                    "function `median(nums)` returning the median of an odd-length "
                    "list without modifying the input. Return only a Python code block."),
            expected_format="python code block",
            scoring_method=ScoringMethod.CODE_PASS,
            expected={"tests": [
                {"name": "odd", "expression": "median([3, 1, 2])", "expected": "2"},
                {"name": "unsorted", "expression": "median([9, 7, 8, 5, 6])", "expected": "7"},
                {"name": "no-mutation", "expression": "(lambda src: (median(src), src[0])[1])([3, 1, 2]) == 3 and median([3, 1, 2]) == 2", "expected": "True"},
            ]},
            evaluator="sandboxed unit tests incl. regression check",
            difficulty="medium", timeout_s=120.0,
            safety_class=SafetyClass.SANDBOXED, style="SWE-bench-style",
        ),
    ]
