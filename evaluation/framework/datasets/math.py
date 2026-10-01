from __future__ import annotations
"""Mathematics datasets with deterministic verification (Phase 4)."""

from typing import List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _task(**kwargs) -> EvalTask:
    kwargs.setdefault("suite", "math")
    kwargs.setdefault("category", EvalCategory.MATH)
    kwargs.setdefault("safety_class", SafetyClass.READ_ONLY)
    kwargs.setdefault("evaluator", "deterministic numeric verification")
    return EvalTask(**kwargs)


def math_tasks() -> List[EvalTask]:
    """Arithmetic, algebra, geometry, word problems, multi-step.

    Every expected answer is recomputed by the deterministic scorer:
    credit requires the exact recomputed value, never plausibility.
    """
    return [
        _task(
            task_id="math-arithmetic-001",
            prompt="Calculate 25 * 4 + 17. Give only the final number.",
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 117, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="GSM8K-style",
        ),
        _task(
            task_id="math-arithmetic-002",
            prompt="Calculate (3 + 5) * 2^3 - 14 / 7. Give only the final number.",
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 60, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="GSM8K-style",
        ),
        _task(
            task_id="math-algebra-003",
            prompt="Solve for x: 5x - 7 = 2x + 14. Give only the value of x.",
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 7, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="MATH-style",
        ),
        _task(
            task_id="math-algebra-004",
            prompt="If f(x) = 3x^2 - 2x + 1, what is f(4)? Give only the number.",
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 41, "tolerance": 0.0},
            difficulty="medium", timeout_s=60.0, style="MATH-style",
        ),
        _task(
            task_id="math-geometry-005",
            prompt=("A right triangle has legs 6 and 8. What is the length of the "
                    "hypotenuse? Give only the number."),
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 10, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="MATH-style",
        ),
        _task(
            task_id="math-geometry-006",
            prompt=("A circle has circumference 31.4159 (use pi = 3.14159). "
                    "What is its radius? Give only the number."),
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 5.0, "tolerance": 0.001},
            difficulty="medium", timeout_s=60.0, style="MATH-style",
        ),
        _task(
            task_id="math-wordproblem-007",
            prompt=("A train travels 60 km in the first hour, 72 km in the second, "
                    "and 55 km in the third. What was its average speed in km/h? "
                    "Give only the number."),
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 62.3333, "tolerance": 0.01},
            difficulty="medium", timeout_s=90.0, style="GSM8K-style",
        ),
        _task(
            task_id="math-wordproblem-008",
            prompt=("A shop discounts a 240 item by 25%, then adds 10% tax on the "
                    "discounted price. What is the final price? Give only the number."),
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 198.0, "tolerance": 0.001},
            difficulty="medium", timeout_s=90.0, style="GSM8K-style",
        ),
        _task(
            task_id="math-multistep-009",
            prompt=("Compute: the sum of all integers from 1 to 100, minus the sum "
                    "of all even numbers from 1 to 100. Give only the number."),
            expected_format="a single number",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 2500, "tolerance": 0.0},
            difficulty="medium", timeout_s=120.0, style="FrontierMath-style",
        ),
        _task(
            task_id="math-exact-010",
            prompt=("What is 2 raised to the power 16? Give only the exact integer."),
            expected_format="a single integer",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 65536, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="FrontierMath-style",
        ),
    ]
