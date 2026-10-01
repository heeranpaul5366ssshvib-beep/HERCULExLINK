from __future__ import annotations
"""Dataset package: benchmark-style suites registered with the registry.

All tasks are original HERCULE items. Style labels (MMLU-style,
GPQA-style, ...) describe format inspiration only — no official
benchmark protocol is claimed or reproduced.
"""

from evaluation.framework.registry import register_suite
from evaluation.framework.task import EvalCategory


@register_suite(
    suite_id="knowledge",
    title="General knowledge & academic reasoning",
    category=EvalCategory.GENERAL_KNOWLEDGE,
    description="MMLU/MMLU-Pro/GPQA/HLE-style original multiple-choice and exact-answer items.",
    style_labels=["MMLU-style", "MMLU-Pro-style", "GPQA-style", "HLE-style"],
)
def _knowledge():
    from evaluation.framework.datasets.knowledge import knowledge_tasks
    return knowledge_tasks()


@register_suite(
    suite_id="reasoning",
    title="Step-by-step reasoning",
    category=EvalCategory.REASONING,
    description="BBH/BBEH/ARC-AGI/FrontierMath-style reasoning on observable outputs.",
    style_labels=["BBH-style", "BBEH-style", "ARC-AGI-style", "FrontierMath-style"],
)
def _reasoning():
    from evaluation.framework.datasets.reasoning import reasoning_tasks
    return reasoning_tasks()


@register_suite(
    suite_id="math",
    title="Mathematics (deterministic verification)",
    category=EvalCategory.MATH,
    description="GSM8K/MATH/FrontierMath-style items scored against recomputed answers.",
    style_labels=["GSM8K-style", "MATH-style", "FrontierMath-style"],
)
def _math():
    from evaluation.framework.datasets.math import math_tasks
    return math_tasks()


@register_suite(
    suite_id="coding",
    title="Coding (sandboxed tests)",
    category=EvalCategory.CODING,
    description="HumanEval/MBPP/LiveCodeBench/SWE-bench-style generation scored in the isolated sandbox.",
    style_labels=["HumanEval-style", "MBPP-style", "LiveCodeBench-style", "SWE-bench-style"],
)
def _coding():
    from evaluation.framework.datasets.coding import coding_tasks
    return coding_tasks()


@register_suite(
    suite_id="truthfulness",
    title="Truthfulness & hallucination resistance",
    category=EvalCategory.TRUTHFULNESS,
    description="TruthfulQA/FEVER-style known/unknown/ambiguous honesty cases.",
    style_labels=["TruthfulQA-style", "FEVER-style"],
)
def _truthfulness():
    from evaluation.framework.datasets.truthfulness import truthfulness_tasks
    return truthfulness_tasks()


@register_suite(
    suite_id="safety",
    title="Safety (deny-only credit)",
    category=EvalCategory.SAFETY,
    description="Refusal, jailbreak, traversal, unsafe tool-use, privacy and injection probes through the real policy path.",
    style_labels=["harmful-request refusal", "jailbreak resistance", "prompt-injection"],
)
def _safety():
    from evaluation.framework.datasets.safety import safety_tasks
    return safety_tasks()


@register_suite(
    suite_id="multilingual",
    title="Multilingual understanding",
    category=EvalCategory.MULTILINGUAL,
    description="Equivalent known-answer and math tasks across supported languages.",
    style_labels=["multilingual knowledge", "multilingual math"],
)
def _multilingual():
    from evaluation.framework.datasets.multilingual import multilingual_tasks
    return multilingual_tasks()


@register_suite(
    suite_id="multimodal",
    title="Multimodal (capability-gated)",
    category=EvalCategory.MULTIMODAL,
    description="Vision tasks only when a real vision capability exists; otherwise skipped honestly.",
    style_labels=["multimodal OCR-style"],
)
def _multimodal():
    from evaluation.framework.datasets.multimodal import multimodal_tasks
    return multimodal_tasks()


@register_suite(
    suite_id="agentic",
    title="Agentic execution (real pipeline)",
    category=EvalCategory.AGENTIC,
    description="Filesystem, tool-use, recovery and honesty tasks through Brain.run_cycle.",
    style_labels=["tool use", "filesystem", "recovery", "failure honesty"],
)
def _agentic():
    from evaluation.framework.datasets.agentic import agentic_tasks
    return agentic_tasks()


@register_suite(
    suite_id="hercule_internal",
    title="HERCULE architecture evaluations",
    category=EvalCategory.HERCULE_INTERNAL,
    description="Routing, memory, capability, planning-contract and voice-routing probes (Phase 3).",
    style_labels=["conversation routing", "memory", "planning contract", "voice routing"],
)
def _hercule_internal():
    from evaluation.framework.datasets.hercule_internal import hercule_internal_tasks
    return hercule_internal_tasks()


@register_suite(
    suite_id="uai_core",
    title="HERCULE Core Benchmark v1 (deterministic control plane)",
    category=EvalCategory.HERCULE_INTERNAL,
    description="UAI Phase M6: deterministic planning/tool/verification/memory tasks; green without any LLM.",
    style_labels=["control-plane benchmark"],
)
def _uai_core():
    from evaluation.framework.datasets.uai_core import uai_core_tasks
    return uai_core_tasks()


@register_suite(
    suite_id="uai_skills",
    title="Skill integration benchmark (UAI Phase M10)",
    category=EvalCategory.AGENTIC,
    description="Validated-skill selection, rejection, policy/autonomy/verification enforcement, no silent installs.",
    style_labels=["skill selection", "skill rejection", "skill verification"],
)
def _uai_skills():
    from evaluation.framework.datasets.uai_skills import uai_skill_tasks
    return uai_skill_tasks()


@register_suite(
    suite_id="uai_research",
    title="Research evidence benchmark (UAI Phase M11)",
    category=EvalCategory.AGENTIC,
    description="Labeled evidence, uncertainty, conflicts, and unavailable-source honesty through the ability pipeline.",
    style_labels=["evidence labeling", "uncertainty honesty"],
)
def _uai_research():
    from evaluation.framework.datasets.uai_research import uai_research_tasks
    return uai_research_tasks()


@register_suite(
    suite_id="uai_safety",
    title="Safety and policy benchmark (UAI Phase M12)",
    category=EvalCategory.SAFETY,
    description="Denial, approval, injection, traversal, autonomy restriction through the real policy path.",
    style_labels=["policy denial", "approval enforcement", "injection resistance"],
)
def _uai_safety():
    from evaluation.framework.datasets.uai_safety import uai_safety_tasks
    return uai_safety_tasks()


@register_suite(
    suite_id="golden_v1",
    title="Golden end-to-end workflows v1 (UAI Phase M13)",
    category=EvalCategory.AGENTIC,
    description="Ten bounded golden workflows: files, math chains, skills, research, denial, recovery.",
    style_labels=["golden workflows"],
)
def _golden_v1():
    from evaluation.framework.datasets.golden_v1 import golden_v1_tasks
    return golden_v1_tasks()


def multimodal_tasks_for(services=None):
    """Loader hook used by the runner when a services dict is available."""
    from evaluation.framework.datasets.multimodal import multimodal_tasks
    return multimodal_tasks(services)
