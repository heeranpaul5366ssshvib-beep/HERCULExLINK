from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Sentence-Transformers Embedding Provider
Author: Heeran Paul
License: MIT
--------------------------------------------

Production-capable local embedding provider. The dependency is lazy:
when ``sentence-transformers`` (or the model weights) cannot load, the
provider reports honestly unavailable and every inference call raises
``EmbeddingUnavailableError`` — fake vectors are never produced.

Vectors leave L2-normalized exactly once (``normalize_embeddings=True``).
"""

import threading
import time
from typing import Any, Dict, List, Optional

from models.embeddings.provider import (
    EmbeddingMalformedError,
    EmbeddingUnavailableError,
    EmbeddingProvider,
    validate_vector,
)

try:
    from sentence_transformers import SentenceTransformer as _STModel

    _HAS_ST = True
except Exception:
    _STModel = None  # type: ignore
    _HAS_ST = False

DEFAULT_ST_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Local transformer embeddings with lazy model loading."""

    def __init__(
        self,
        model_id: str = DEFAULT_ST_MODEL,
        device: Optional[str] = None,
        batch_size: int = 32,
    ):
        self._model_id = model_id
        self._device = device or "cpu"
        self._batch_size = batch_size
        self._model: Any = None
        self._load_error: str = ""
        self._lock = threading.Lock()
        self._dimension = 0

    # -- identity -------------------------------------------------
    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return True

    @property
    def device(self) -> str:
        return self._device

    # -- lifecycle ------------------------------------------------
    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if not _HAS_ST:
                self._load_error = "sentence-transformers not installed"
                raise EmbeddingUnavailableError(f"embedding model '{self._model_id}' unavailable: {self._load_error}")
            try:
                self._model = _STModel(self._model_id, device=self._device)
                dimension_fn = getattr(self._model, "get_embedding_dimension", None) or getattr(
                    self._model, "get_sentence_embedding_dimension", None
                )
                self._dimension = int(dimension_fn())
            except Exception as exc:
                self._load_error = str(exc)
                self._model = None
                raise EmbeddingUnavailableError(f"embedding model '{self._model_id}' unavailable: {exc}")
            return self._model

    def available(self) -> bool:
        if self._model is not None:
            return True
        if not _HAS_ST:
            return False
        try:
            self._ensure_loaded()
            return True
        except EmbeddingUnavailableError:
            return False

    def health(self) -> Dict[str, Any]:
        return {
            "status": "healthy" if self.available() else "unavailable",
            "available": self.available(),
            "model_id": self._model_id,
            "dimension": self._dimension,
            "normalized": True,
            "device": self._device,
            "test_only": False,
            "reason": self._load_error if not self.available() else "",
        }

    # -- inference ------------------------------------------------
    def embed(self, text: str) -> List[float]:
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not isinstance(texts, list) or any(not isinstance(t, str) for t in texts):
            raise EmbeddingMalformedError("embed_batch expects list[str]")
        if not texts:
            return []
        model = self._ensure_loaded()
        started = time.perf_counter()
        try:
            raw = model.encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise EmbeddingUnavailableError(f"embedding inference failed for '{self._model_id}': {exc}")
        latency_ms = (time.perf_counter() - started) * 1000.0
        vectors = [validate_vector(list(map(float, row)), self._dimension or 0, "st-embed") for row in raw]
        self.last_batch_latency_ms = latency_ms
        self.last_batch_size = len(texts)
        return vectors
