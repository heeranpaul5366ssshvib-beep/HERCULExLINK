from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional

from cognition.attention.attention_engine import AttentionEngine
from cognition.context.priority import BudgetConfig, apply_budgets, classify_priority, default_count_tokens


class ContextEngine:
    """Build and rank a compact, traceable context payload for the current task."""

    def __init__(
        self,
        memory=None,
        knowledge=None,
        tools=None,
        system=None,
        environment=None,
        task_state=None,
        max_tokens: int = 512,
        token_budget: Optional[int] = None,
        attention_engine: Optional[AttentionEngine] = None,
        budget_config: Optional[BudgetConfig] = None,
    ):
        self.memory = memory
        self.knowledge = knowledge
        self.tools = tools or []
        self.system = system or {}
        self.environment = environment or {}
        self.task_state = task_state or {}
        self.max_tokens = token_budget or max_tokens
        self.attention = attention_engine or AttentionEngine()
        self.budget_config = budget_config
        self._last_context = {}
        self._last_diagnostics: List[Dict[str, Any]] = []

    @staticmethod
    def _make_correlation_id(prefix: str = "ctx") -> str:
        return f"{prefix}-{hashlib.sha1(str(hash((prefix, __import__('time').time()))).encode('utf-8')).hexdigest()[:12]}"

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 400) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3].rstrip() + "..."

    def _normalize_item(self, source: str, text: str, metadata: Optional[Dict[str, Any]] = None, **extras):
        meta = dict(metadata or {})
        meta.update(extras)
        item = {
            "source": source,
            "text": self._truncate_text(str(text), 400),
            "relevance": float(meta.get("relevance", meta.get("score", 0.0))),
            "recency": float(meta.get("recency", 0.0)),
            "importance": float(meta.get("importance", 0.0)),
            "confidence": float(meta.get("confidence", 0.0)),
            "relationship": float(meta.get("relationship", 0.0)),
            "metadata": meta,
        }
        if "timestamp" in meta:
            item["timestamp"] = meta["timestamp"]
        if "task_id" in meta:
            item["task_id"] = meta["task_id"]
        return item

    def _collect_memory_items(self, prompt: str):
        items = []
        if self.memory is None:
            return items
        try:
            history = self.memory.history() or []
        except Exception:
            history = []
        for entry in history:
            text = entry.get("text") if isinstance(entry, dict) else str(entry)
            if text:
                items.append(self._normalize_item("memory", text, entry, relevance=0.7, recency=0.8, importance=0.6, confidence=0.7))
        try:
            events = self.memory.event_history() or []
        except Exception:
            events = []
        for entry in events:
            text = entry.get("text") if isinstance(entry, dict) else str(entry)
            if text:
                items.append(self._normalize_item("memory_event", text, entry, relevance=0.8, recency=0.9, importance=0.7, confidence=0.8))
        try:
            retrieval = self.memory.retrieval.search(prompt)
        except Exception:
            retrieval = []
        for result in retrieval:
            if isinstance(result, dict):
                text = result.get("text") or result.get("query") or ""
                metadata = result.get("metadata", {})
                items.append(self._normalize_item("retrieval", text, metadata, relevance=float(metadata.get("importance", 0.6)), recency=float(metadata.get("recency", 0.5)), importance=float(metadata.get("importance", 0.7)), confidence=float(metadata.get("confidence", 0.7)), relationship=1.0))
        return items

    def _collect_knowledge_items(self, prompt: str):
        items = []
        if self.knowledge is None:
            return items
        try:
            results = self.knowledge.keyword_search(prompt)
        except Exception:
            results = []
        for result in results:
            if isinstance(result, dict):
                text = result.get("text") or ""
                metadata = result.get("metadata", {})
                items.append(self._normalize_item("knowledge", text, metadata, relevance=float(metadata.get("importance", 0.7)), recency=float(metadata.get("recency", 0.5)), importance=float(metadata.get("importance", 0.8)), confidence=float(metadata.get("confidence", 0.7)), relationship=0.9))
        return items

    def _collect_task_items(self, prompt: str):
        items = []
        if isinstance(self.task_state, dict):
            if self.task_state.get("goal"):
                items.append(self._normalize_item("task", str(self.task_state["goal"]), self.task_state, relevance=1.0, recency=1.0, importance=1.0, confidence=1.0, relationship=1.0, task_id=self.task_state.get("id")))
            if self.task_state.get("instructions"):
                items.append(self._normalize_item("task_instructions", str(self.task_state["instructions"]), self.task_state, relevance=1.0, recency=1.0, importance=1.0, confidence=1.0, relationship=1.0))
        if prompt:
            items.append(self._normalize_item("current_request", prompt, {"source": "user"}, relevance=1.0, recency=1.0, importance=1.0, confidence=1.0, relationship=1.0))
        return items

    def _collect_system_items(self):
        items = []
        if self.system:
            text = json.dumps(self.system, sort_keys=True)
            items.append(self._normalize_item("system", text, self.system, relevance=0.6, recency=0.7, importance=0.5, confidence=0.9, relationship=0.8))
        if self.environment:
            text = json.dumps(self.environment, sort_keys=True)
            items.append(self._normalize_item("environment", text, self.environment, relevance=0.7, recency=0.7, importance=0.6, confidence=0.8, relationship=0.8))
        return items

    def _collect_tool_items(self):
        items = []
        for tool in self.tools:
            if isinstance(tool, dict):
                name = tool.get("name") or tool.get("id") or "tool"
                description = tool.get("description") or ""
                item_text = f"Tool: {name}. {description}".strip()
                if item_text:
                    items.append(self._normalize_item("tool", item_text, tool, relevance=0.5, recency=0.6, importance=0.7, confidence=0.8, relationship=0.7))
        return items

    def _deduplicate(self, items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []
        for item in items:
            key = (item.get("source"), item.get("text"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _budget(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not items:
            return []
        ranked = self.attention.rank(items)
        selected = []
        total_tokens = 0
        for item in ranked:
            text = str(item.get("text", ""))
            approx_tokens = max(1, len(text.split()) + 10)
            if total_tokens + approx_tokens > self.max_tokens:
                if not selected:
                    selected.append(item)
                break
            selected.append(item)
            total_tokens += approx_tokens
        return selected

    def build_context(self, prompt: str, correlation_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        correlation_id = correlation_id or self._make_correlation_id("ctx")
        budget_config = kwargs.get("budget_config") or self.budget_config
        items = []
        items.extend(self._collect_task_items(prompt))
        items.extend(self._collect_memory_items(prompt))
        items.extend(self._collect_knowledge_items(prompt))
        items.extend(self._collect_tool_items())
        items.extend(self._collect_system_items())
        items = self._deduplicate(items)
        ranked = self.attention.rank(items)
        prioritized = self.attention.filter_irrelevant(ranked, minimum=0.15)
        for item in prioritized:
            item["priority"] = classify_priority(item).value
        diagnostics: List[Dict[str, Any]] = []
        if budget_config is not None:
            budgeted, diagnostics = apply_budgets(prioritized, budget_config, default_count_tokens)
        else:
            budgeted = self._budget(prioritized)
        self._last_diagnostics = diagnostics
        payload = {
            "correlation_id": correlation_id,
            "task_id": self.task_state.get("id") if isinstance(self.task_state, dict) else None,
            "prompt": prompt,
            "items": budgeted,
            "token_budget": budget_config.total_tokens if budget_config is not None else self.max_tokens,
            "token_usage": sum(max(1, len(str(item.get("text", "")).split()) + 10) for item in budgeted),
            "sources": sorted({item["source"] for item in budgeted}),
            "priorities": sorted({str(item.get("priority", "unknown")) for item in budgeted}),
            "diagnostics": diagnostics,
            "observability": {
                "item_count": len(budgeted),
                "raw_count": len(items),
                "correlation_id": correlation_id,
                "task_id": self.task_state.get("id") if isinstance(self.task_state, dict) else None,
            },
        }
        self._last_context = payload
        return payload
