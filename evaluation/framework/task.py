from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Task Schema
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured metadata for one evaluation task. Tasks are pure data: they
declare a prompt, the expected format, the scoring method and the
safety class, and carry no execution logic. Categories are benchmark-
*inspired* labels (MMLU-style, GPQA-style, ...) — never claims of
official benchmark participation.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EvalCategory(str, Enum):
    GENERAL_KNOWLEDGE = "GENERAL_KNOWLEDGE"
    REASONING = "REASONING"
    MATH = "MATH"
    CODING = "CODING"
    TRUTHFULNESS = "TRUTHFULNESS"
    SAFETY = "SAFETY"
    MULTILINGUAL = "MULTILINGUAL"
    MULTIMODAL = "MULTIMODAL"
    AGENTIC = "AGENTIC"
    HERCULE_INTERNAL = "HERCULE_INTERNAL"


class SafetyClass(str, Enum):
    """How the runner must treat a task.

    READ_ONLY   — no side effects, always parallelizable.
    SANDBOXED   — generated code runs only in the isolated subprocess.
    ACTIVE      — touches the real filesystem sandbox / abilities;
                  never run concurrently with other ACTIVE tasks.
    """

    READ_ONLY = "READ_ONLY"
    SANDBOXED = "SANDBOXED"
    ACTIVE = "ACTIVE"


class ScoringMethod(str, Enum):
    EXACT_MATCH = "exact_match"
    CONTAINS_ANY = "contains_any"
    REGEX = "regex"
    NUMERIC_WITHIN = "numeric_within"
    CODE_PASS = "code_pass"
    SAFETY_REFUSAL = "safety_refusal"
    HONESTY = "honesty"
    ROUTING = "routing"
    RECORD_ROUTE = "record_route"
    AGENTIC = "agentic"
    CAPABILITY_GATED = "capability_gated"
    RESEARCH_EVIDENCE = "research_evidence"


class Outcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class EvalTask:
    """One benchmark-style evaluation task (pure metadata)."""

    task_id: str
    category: EvalCategory
    suite: str
    prompt: str
    expected_format: str
    scoring_method: ScoringMethod
    expected: Any = None          # scoring payload (answer, letters, keywords, code tests...)
    evaluator: str = ""           # human-readable evaluator description
    difficulty: str = "medium"    # easy | medium | hard | expert
    timeout_s: float = 120.0
    required_capabilities: List[str] = field(default_factory=list)
    safety_class: SafetyClass = SafetyClass.READ_ONLY
    style: str = ""               # benchmark-inspired label, e.g. "MMLU-style"
    notes: str = ""
    # UAI Phase M2: declarative execution contract (all optional).
    input: Any = None             # task input payload where applicable
    expected_behavior: str = ""   # human-readable expected behavior
    success_criteria: str = ""    # human-readable pass conditions
    failure_conditions: str = ""  # human-readable fail conditions
    allowed_tools: List[str] = field(default_factory=list)
    prohibited_tools: List[str] = field(default_factory=list)
    autonomy_level: Optional[int] = None  # required autonomy gate, if any
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["category"] = self.category.value
        data["scoring_method"] = self.scoring_method.value
        data["safety_class"] = self.safety_class.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalTask":
        payload = dict(data or {})
        payload["category"] = EvalCategory(str(payload.get("category", "")))
        payload["scoring_method"] = ScoringMethod(str(payload.get("scoring_method", "")))
        payload["safety_class"] = SafetyClass(str(payload.get("safety_class", SafetyClass.READ_ONLY.value)))
        known = {f for f in cls.__dataclass_fields__ if f != "evaluator"}  # evaluator is descriptive only
        return cls(**{k: v for k, v in payload.items() if k in known})


@dataclass
class SuiteSpec:
    """A named collection of evaluation tasks."""

    suite_id: str
    title: str
    category: EvalCategory
    description: str = ""
    style_labels: List[str] = field(default_factory=list)
    loader: Optional[Callable[[], List[EvalTask]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "title": self.title,
            "category": self.category.value,
            "description": self.description,
            "style_labels": list(self.style_labels),
        }
