from __future__ import annotations
"""Suite definitions over the registered datasets.

Importing this package registers every built-in suite with the
evaluation registry. QUICK_SUITES is the fast smoke set; FULL_SUITES
is the complete evaluation.
"""

from typing import List

from evaluation.framework import datasets as _datasets  # noqa: F401  (registers suites)

QUICK_SUITES: List[str] = ["math", "reasoning", "hercule_internal"]
FULL_SUITES: List[str] = [
    "knowledge", "reasoning", "math", "coding", "truthfulness",
    "safety", "multilingual", "multimodal", "agentic", "hercule_internal",
]
COMPARE_SUITES: List[str] = ["math", "reasoning"]  # READ_ONLY default for model comparison
UAI_SUITES: List[str] = [  # UAI Phase M: deterministic control-plane benchmark
    "uai_core", "uai_skills", "uai_research", "uai_safety", "golden_v1",
]


def resolve_suites(names: List[str], mode: str = "quick") -> List[str]:
    """Resolve requested suite names (empty -> mode default)."""
    if names:
        return list(names)
    return list(QUICK_SUITES if mode == "quick" else FULL_SUITES)
