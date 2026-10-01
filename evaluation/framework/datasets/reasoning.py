from __future__ import annotations
"""Reasoning datasets (BBH/BBEH/ARC-AGI/FrontierMath-style, Phase 2 & 6)."""

from typing import List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _task(**kwargs) -> EvalTask:
    kwargs.setdefault("suite", "reasoning")
    kwargs.setdefault("category", EvalCategory.REASONING)
    kwargs.setdefault("safety_class", SafetyClass.READ_ONLY)
    kwargs.setdefault("evaluator", "deterministic scorer")
    return EvalTask(**kwargs)


def reasoning_tasks() -> List[EvalTask]:
    """Multi-hop, constraints, patterns, dependency reasoning (observable
    outputs only — hidden chain-of-thought is never evaluated)."""
    return [
        _task(
            task_id="reasoning-bbh-style-tracking-001",
            prompt=("Track the state: Alex has 2 apples. Ben gives Alex 3 apples. "
                    "Alex eats 1 apple. Claire takes half of Alex's remaining apples. "
                    "How many apples does Alex have now? Answer with the number only."),
            expected_format="a single integer",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 2, "tolerance": 0.0},
            difficulty="easy", timeout_s=60.0, style="BBH-style",
        ),
        _task(
            task_id="reasoning-bbh-style-logic-002",
            prompt=("Three boxes: red, blue, green. Exactly one contains a gem. "
                    "Clue 1: The gem is not in red. Clue 2: If the gem is in blue, "
                    "then it is in green. Exactly one clue is true. Where is the gem? "
                    "Answer with the color name only."),
            expected_format="a color word",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["blue"],
            difficulty="medium", timeout_s=90.0, style="BBH-style",
        ),
        _task(
            task_id="reasoning-bbeh-style-constraints-003",
            prompt=("Order the runners: Ana finished before Bo but after Cy. "
                    "Dee finished last. List the runners from first to last as "
                    "comma-separated names."),
            expected_format="comma-separated names in order",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["cy, ana, bo, dee", "cy,ana,bo,dee", "cy, ana, bo, dee."],
            difficulty="easy", timeout_s=60.0, style="BBEH-style",
        ),
        _task(
            task_id="reasoning-arcagi-style-pattern-004",
            prompt=("Pattern transformation: input grid rows become output grid rows "
                    "by shifting every row one step to the right with wrap-around. "
                    "Input rows: [1,2,3] [4,5,6]. What is the output grid? "
                    "Answer as two rows of numbers."),
            expected_format="two rows of numbers",
            scoring_method=ScoringMethod.CONTAINS_ANY,
            expected=["3,1,2", "3 1 2"],
            difficulty="medium", timeout_s=90.0, style="ARC-AGI-style",
        ),
        _task(
            task_id="reasoning-frontiermath-style-005",
            prompt=("How many integers between 1 and 1000 inclusive are divisible "
                    "by neither 2 nor 3 nor 5? Give the exact number."),
            expected_format="a single integer",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 266, "tolerance": 0.0},
            difficulty="medium", timeout_s=120.0, style="FrontierMath-style",
        ),
        _task(
            task_id="reasoning-ambiguity-006",
            prompt=("A town has two barbers. Barber A shaves only those who do not "
                    "shave themselves; Barber B shaves everyone who does not shave "
                    "themselves. Which single question below is answerable from the "
                    "given information alone?\n"
                    "1) Who shaves Barber A?\n2) Does Barber B shave himself?\n"
                    "3) Who shaves Barber B?\n4) How many barbers are in the town?\n"
                    "Answer with a digit 1-4 only."),
            expected_format="a single digit",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["4"],
            difficulty="hard", timeout_s=120.0, style="BBEH-style",
        ),
    ]
