from __future__ import annotations
"""Original, hermetic evaluation datasets for HERCULE internal evaluation.

Every task here is an original benchmark-*style* item written for
HERCULE (no copyrighted benchmark data is reproduced or downloaded).
Labels such as "MMLU-style" describe the *format inspiration* only —
they are never claims of official benchmark participation.
"""

from typing import List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def _task(**kwargs) -> EvalTask:
    kwargs.setdefault("suite", "knowledge")
    kwargs.setdefault("category", EvalCategory.GENERAL_KNOWLEDGE)
    kwargs.setdefault("safety_class", SafetyClass.READ_ONLY)
    kwargs.setdefault("evaluator", "deterministic scorer")
    return EvalTask(**kwargs)


def knowledge_tasks() -> List[EvalTask]:
    """MMLU/MMLU-Pro/GPQA/HLE-style academic questions (original items)."""
    return [
        _task(
            task_id="knowledge-mmlu-style-biology-001",
            prompt=("Multiple choice: Which organelle synthesizes most of the ATP "
                    "in a eukaryotic cell?\nA) Ribosome\nB) Mitochondrion\n"
                    "C) Golgi apparatus\nD) Lysosome\nRespond with only the letter."),
            expected_format="single letter A-D",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["b"],
            evaluator="exact match on choice letter",
            difficulty="easy", timeout_s=60.0,
            required_capabilities=[], style="MMLU-style",
        ),
        _task(
            task_id="knowledge-mmlu-style-history-002",
            prompt=("Multiple choice: The Treaty of Westphalia (1648) is best known "
                    "for ending which conflict?\nA) Hundred Years' War\nB) Thirty Years' War\n"
                    "C) War of Spanish Succession\nD) Napoleonic Wars\nRespond with only the letter."),
            expected_format="single letter A-D",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["b"],
            difficulty="easy", timeout_s=60.0, style="MMLU-style",
        ),
        _task(
            task_id="knowledge-mmlu-style-physics-003",
            prompt=("Multiple choice: A satellite in a stable circular orbit accelerates "
                    "tangentially. Its new orbit (before any other force acts) becomes:\n"
                    "A) circular at the same radius\nB) elliptical with higher apoapsis\n"
                    "C) elliptical with lower periapsis\nD) it immediately escapes\n"
                    "Respond with only the letter."),
            expected_format="single letter A-D",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["b"],
            difficulty="medium", timeout_s=90.0, style="MMLU-style",
        ),
        _task(
            task_id="knowledge-mmlupro-style-logic-004",
            prompt=("Multiple choice (may require multi-step reasoning): All bloops are "
                    "razzies. All razzies are lazzies. Some lazzies are not razzy."
                    "Which statement MUST be true?\n"
                    "A) All bloops are lazzies\nB) Some bloops are not lazzies\n"
                    "C) No lazzie is a bloop\nD) Some razzies are not lazzies\n"
                    "Respond with only the letter."),
            expected_format="single letter A-D",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["a"],
            difficulty="medium", timeout_s=90.0, style="MMLU-Pro-style",
        ),
        _task(
            task_id="knowledge-gpqa-style-chem-005",
            prompt=("Graduate-level multiple choice: In kinetic isotope effects, replacing H "
                    "with D in a bond being broken in the rate-determining step typically "
                    "gives kH/kD closest to:\nA) 0.7\nB) 1.0\nC) 7\nD) 700\n"
                    "Respond with only the letter."),
            expected_format="single letter A-D",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["c"],
            difficulty="hard", timeout_s=120.0, style="GPQA-style",
        ),
        _task(
            task_id="knowledge-hle-style-frontier-006",
            prompt=("Frontier-style reasoning: A perfect digit-sum machine writes integers "
                    "from 1 upward, concatenated (123456789101112...). The one-millionth "
                    "digit it writes belongs to which integer? Give only that integer."),
            expected_format="a single integer",
            scoring_method=ScoringMethod.NUMERIC_WITHIN,
            expected={"answer": 185185, "tolerance": 0.0},
            difficulty="expert", timeout_s=180.0, style="HLE-style",
        ),
    ]
