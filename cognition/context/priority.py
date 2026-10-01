from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Context Priority Classes & Budgets
Author: Heeran Paul
License: MIT
--------------------------------------------

CRITICAL   system/task identity — never dropped for size.
IMPORTANT  high-signal items — dropped only after all lower classes.
RELEVANT   useful supporting items.
OPTIONAL   nice-to-have filler.
DISCARDABLE below the relevance floor.

``apply_budgets`` enforces an explicit token budget plus optional
per-source caps, returning the selected items and a diagnostic trail
explaining every removal/compression.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

_CRITICAL_SOURCES = {"current_request", "task", "task_instructions", "system"}


class PriorityClass(str, Enum):
    CRITICAL = "critical"
    IMPORTANT = "important"
    RELEVANT = "relevant"
    OPTIONAL = "optional"
    DISCARDABLE = "discardable"


@dataclass
class BudgetConfig:
    total_tokens: int = 512
    per_source_tokens: Dict[str, int] = field(default_factory=dict)
    protected: Tuple[str, ...] = (PriorityClass.CRITICAL.value,)
    compress: bool = True
    compressed_chars: int = 200


def classify_priority(item: Dict[str, Any]) -> PriorityClass:
    """Deterministic priority from source + attention/relevance signals."""
    source = str(item.get("source", ""))
    if source in _CRITICAL_SOURCES:
        return PriorityClass.CRITICAL
    score = float(item.get("attention_score", item.get("relevance", 0.0)) or 0.0)
    relevance = float(item.get("relevance", 0.0) or 0.0)
    if score >= 0.7 or relevance >= 0.8:
        return PriorityClass.IMPORTANT
    if score >= 0.4:
        return PriorityClass.RELEVANT
    if score >= 0.15:
        return PriorityClass.OPTIONAL
    return PriorityClass.DISCARDABLE


def default_count_tokens(text: str) -> int:
    return max(1, len(str(text).split()) + 10)


def apply_budgets(
    ranked_items: List[Dict[str, Any]],
    budget: BudgetConfig,
    count_tokens: Optional[Callable[[str], int]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Filter -> deduplicate-assumed -> budget -> order.

    ``ranked_items`` must already be rank-ordered (best first); selection
    preserves that order. Returns (selected, diagnostics).
    """
    count = count_tokens or default_count_tokens
    diagnostics: List[Dict[str, Any]] = []
    tagged: List[Dict[str, Any]] = []
    for item in ranked_items:
        entry = dict(item)
        entry["priority"] = classify_priority(entry).value
        tagged.append(entry)

    protected = [i for i in tagged if i["priority"] in budget.protected]
    rest = [i for i in tagged if i["priority"] not in budget.protected]
    dropped_classes = {i["priority"] for i in tagged if i["priority"] == PriorityClass.DISCARDABLE.value}
    candidates = protected + [i for i in rest if i["priority"] != PriorityClass.DISCARDABLE.value]
    for priority in sorted(dropped_classes):
        diagnostics.append({"action": "removed", "priority": priority, "reason": "below relevance floor"})

    # Per-source caps (protected items bypass caps).
    if budget.per_source_tokens:
        usage: Dict[str, int] = {}
        capped: List[Dict[str, Any]] = []
        for item in candidates:
            if item["priority"] in budget.protected:
                capped.append(item)
                continue
            source = str(item.get("source", ""))
            cap = budget.per_source_tokens.get(source)
            cost = count(str(item.get("text", "")))
            if cap is not None and usage.get(source, 0) + cost > cap:
                diagnostics.append({"action": "removed", "source": source, "priority": item["priority"], "reason": f"per-source cap {cap}"})
                continue
            usage[source] = usage.get(source, 0) + cost
            capped.append(item)
        candidates = capped

    # Total budget in rank order; protected items always fit at least one.
    selected: List[Dict[str, Any]] = []
    total = 0
    for item in candidates:
        cost = count(str(item.get("text", "")))
        if total + cost > budget.total_tokens:
            if item["priority"] in budget.protected:
                if budget.compress:
                    # Compress the protected item itself rather than dropping it.
                    remaining = budget.total_tokens - total
                    words = str(item.get("text", "")).split()
                    keep = max(1, remaining - 10)
                    item["text"] = " ".join(words[:keep]) + ("..." if len(words) > keep else "")
                    item["compressed"] = True
                    selected.append(item)
                    total += count(item["text"])
                    diagnostics.append({"action": "compressed", "source": item.get("source"), "priority": item["priority"], "reason": "protected item over budget"})
                elif not selected:
                    selected.append(item)
                    total += cost
                    diagnostics.append({"action": "kept-over-budget", "source": item.get("source"), "priority": item["priority"], "reason": "protected item"})
                else:
                    diagnostics.append({"action": "removed", "source": item.get("source"), "priority": item["priority"], "reason": f"total budget {budget.total_tokens}"})
            else:
                diagnostics.append({"action": "removed", "source": item.get("source"), "priority": item["priority"], "reason": f"total budget {budget.total_tokens}"})
            continue
        selected.append(item)
        total += cost

    # Optional compression of the lowest-priority selections.
    if budget.compress:
        for item in reversed(selected):
            if total <= budget.total_tokens:
                break
            if item["priority"] in budget.protected:
                continue
            text = str(item.get("text", ""))
            if len(text) > budget.compressed_chars:
                item["text"] = text[: budget.compressed_chars].rstrip() + "..."
                item["compressed"] = True
                total = sum(count(str(i.get("text", ""))) for i in selected)
                diagnostics.append({"action": "compressed", "source": item.get("source"), "priority": item["priority"], "reason": "fit total budget"})

    # Order: protected first (rank order), then the rest in rank order.
    order = {PriorityClass.CRITICAL.value: 0, PriorityClass.IMPORTANT.value: 1, PriorityClass.RELEVANT.value: 2, PriorityClass.OPTIONAL.value: 3}
    selected.sort(key=lambda i: order.get(i.get("priority", ""), 4))
    return selected, diagnostics
