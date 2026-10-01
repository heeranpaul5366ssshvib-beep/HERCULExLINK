from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Embedding Cache
Author: Heeran Paul
License: MIT
--------------------------------------------

Content-addressed cache. The key binds text hash + model identity +
configuration version, so embeddings are NEVER reused across
incompatible models. Hits re-validate dimension before returning.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from models.embeddings.provider import (
    EmbeddingDimensionMismatchError,
    text_fingerprint,
)


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {"hits": self.hits, "misses": self.misses, "hit_rate": round(self.hit_rate, 3)}


class EmbeddingCache:
    """In-memory embedding cache with model-bound keys."""

    def __init__(self, version: str = "1"):
        self.version = version
        self._store: Dict[str, Tuple[List[float], int]] = {}
        self.stats = CacheStats()

    def key(self, text: str, model_id: str) -> str:
        return f"{text_fingerprint(text)}|{model_id}|v{self.version}"

    def get(self, text: str, model_id: str, expected_dim: int = 0) -> Optional[List[float]]:
        entry = self._store.get(self.key(text, model_id))
        if entry is None:
            self.stats.misses += 1
            return None
        vector, dim = entry
        if expected_dim and dim != expected_dim:
            # Stale entry from an incompatible model build: evict, miss.
            self._store.pop(self.key(text, model_id), None)
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return list(vector)

    def put(self, text: str, model_id: str, vector: List[float]) -> None:
        self._store[self.key(text, model_id)] = (list(vector), len(vector))

    def invalidate_model(self, model_id: str) -> int:
        doomed = [k for k in self._store if k.split("|", 2)[1] == model_id]
        for key in doomed:
            self._store.pop(key, None)
        return len(doomed)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
