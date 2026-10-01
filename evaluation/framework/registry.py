from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Evaluation Registry
Author: Heeran Paul
License: MIT
--------------------------------------------

Registry of evaluation suites. Suite modules register themselves with
``@register_suite``; the registry is the single lookup point for the
runner, the CLI and the UI panel. Every suite lists its category and
benchmark-*inspired* style labels (never official-benchmark claims).
"""

from typing import Callable, Dict, List, Optional

from evaluation.framework.task import EvalCategory, EvalTask, SuiteSpec

_SUITE_LOADER: Dict[str, Callable[[], List[EvalTask]]] = {}
_SPECS: Dict[str, SuiteSpec] = {}


def register_suite(
    suite_id: str,
    title: str,
    category: EvalCategory,
    description: str = "",
    style_labels: Optional[List[str]] = None,
) -> Callable[[Callable[[], List[EvalTask]]], Callable[[], List[EvalTask]]]:
    """Class decorator registering a suite loader (imports stay lazy)."""

    def decorator(loader: Callable[[], List[EvalTask]]) -> Callable[[], List[EvalTask]]:
        _SUITE_LOADER[suite_id] = loader
        _SPECS[suite_id] = SuiteSpec(
            suite_id=suite_id, title=title, category=category,
            description=description, style_labels=list(style_labels or []),
            loader=loader)
        return loader

    return decorator


def available_suites() -> List[str]:
    """Import every suite module, then return registered suite ids (sorted)."""
    from evaluation.framework import suites as _suites  # noqa: F401  (registers)
    return sorted(_SPECS)


def suite_spec(suite_id: str) -> SuiteSpec:
    if suite_id not in _SPECS:
        available_suites()
    if suite_id not in _SPECS:
        raise KeyError(f"unknown evaluation suite: {suite_id}")
    return _SPECS[suite_id]


def suite_tasks(suite_id: str) -> List[EvalTask]:
    loader = suite_spec(suite_id).loader
    return list(loader() if callable(loader) else (loader or []))


def suite_count() -> int:
    return len(available_suites())


def suite_ids_for_categories(categories: List[EvalCategory]) -> List[str]:
    wanted = {c.value for c in categories}
    return [sid for sid in available_suites()
            if _SPECS[sid].category.value in wanted]


def registry_report() -> Dict[str, List[Dict[str, object]]]:
    available_suites()
    return [spec.to_dict() for spec in (_SPECS[sid] for sid in sorted(_SPECS))]
