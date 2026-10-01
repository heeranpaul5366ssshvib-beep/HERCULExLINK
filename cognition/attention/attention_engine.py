from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence


class AttentionEngine:
    """Rank context items by relevance, recency, importance, and confidence."""

    def __init__(self, weights: Dict[str, float] | None = None):
        self.weights = {
            "relevance": 0.40,
            "recency": 0.15,
            "importance": 0.20,
            "confidence": 0.15,
            "relationship": 0.10,
        }
        if weights:
            self.weights.update(weights)

    def score(self, item: Dict[str, Any]) -> float:
        relevance = float(item.get("relevance", item.get("score", 0.0)))
        recency = float(item.get("recency", 0.0))
        importance = float(item.get("importance", 0.0))
        confidence = float(item.get("confidence", 0.0))
        relationship = float(item.get("relationship", 0.0))
        return (
            relevance * self.weights["relevance"]
            + recency * self.weights["recency"]
            + importance * self.weights["importance"]
            + confidence * self.weights["confidence"]
            + relationship * self.weights["relationship"]
        )

    def rank(self, items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ranked = []
        for item in items:
            scored = dict(item)
            scored["attention_score"] = self.score(item)
            ranked.append(scored)
        ranked.sort(key=lambda entry: float(entry.get("attention_score", 0.0)), reverse=True)
        return ranked

    def filter_irrelevant(self, items: Iterable[Dict[str, Any]], minimum: float = 0.15):
        return [item for item in items if self.score(item) >= minimum]
