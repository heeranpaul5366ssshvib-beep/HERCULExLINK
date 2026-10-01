from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Deterministic Hash Embedding Provider
Author: Heeran Paul
License: MIT
--------------------------------------------

Test-grade provider wrapping the deterministic hash embedding.
``test_only`` is True and reported in health: use for hermetic unit
tests and offline demos, never as a production semantic backend.
"""

from typing import Any, Dict, List

from knowledge.ingestion import hash_embed
from models.embeddings.provider import EmbeddingProvider, validate_vector


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic, dependency-free embeddings for tests."""

    def __init__(self, dim: int = 64, model_id: str = "hercule-hash-test-v1"):
        self._dim = dim
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def normalized(self) -> bool:
        return True

    @property
    def test_only(self) -> bool:
        return True

    def available(self) -> bool:
        return True

    def health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "available": True,
            "model_id": self._model_id,
            "dimension": self._dim,
            "normalized": True,
            "test_only": True,
        }

    def embed(self, text: str) -> List[float]:
        if not isinstance(text, str):
            from models.embeddings.provider import EmbeddingMalformedError

            raise EmbeddingMalformedError(f"expected str, got {type(text).__name__}")
        return validate_vector(hash_embed(text, self._dim), self._dim, "hash-embed")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]
