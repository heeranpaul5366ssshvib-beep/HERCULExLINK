from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Embedding Provider Interface
Author: Heeran Paul
License: MIT
--------------------------------------------

The ONE authoritative embedding abstraction. Every backend
(sentence-transformers, Ollama, deterministic test-grade) implements
``EmbeddingProvider``; ``EmbeddingManager`` is the facade that selects,
caches, batches, and observes providers. No second competing
abstraction is introduced — adapter ``embeddings()`` methods and the
legacy ``embed_fn`` callable seam plug into this interface.

Contract:

* input:  single ``str`` / batch ``list[str]``
* output: ``list[float]`` / ``list[list[float]]`` (validated, finite)
* dimensions: fixed per model, declared via ``dimension``
* normalization: performed ONCE by the provider (``normalized=True``);
  downstream cosine scoring is scale-invariant and must not renormalize
  as a correctness requirement
* failures: typed errors below; providers NEVER return fake vectors —
  unavailability raises ``EmbeddingUnavailableError``
"""

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class EmbeddingError(RuntimeError):
    """Base class; carries a machine-readable ``code``."""

    def __init__(self, message: str, code: str = "EMBEDDING_ERROR"):
        super().__init__(message)
        self.code = code


class EmbeddingUnavailableError(EmbeddingError):
    def __init__(self, message: str):
        super().__init__(message, "EMBEDDING_UNAVAILABLE")


class EmbeddingDimensionMismatchError(EmbeddingError):
    def __init__(self, message: str):
        super().__init__(message, "EMBEDDING_DIMENSION_MISMATCH")


class EmbeddingMalformedError(EmbeddingError):
    def __init__(self, message: str):
        super().__init__(message, "EMBEDDING_MALFORMED")


def text_fingerprint(text: str) -> str:
    """Stable id for logs/traces/metrics — never the raw content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def validate_vector(vector: Any, expected_dim: int = 0, where: str = "vector") -> List[float]:
    """Reject malformed vectors loudly: wrong type, bad dim, NaN/Inf."""
    if not isinstance(vector, (list, tuple)):
        raise EmbeddingMalformedError(f"{where}: expected list[float], got {type(vector).__name__}")
    values = list(vector)
    if expected_dim and len(values) != expected_dim:
        raise EmbeddingDimensionMismatchError(
            f"EMBEDDING_DIMENSION_MISMATCH: {where} has dim {len(values)}, expected {expected_dim}"
        )
    if not values:
        raise EmbeddingMalformedError(f"{where}: empty vector")
    for value in values:
        if not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
            raise EmbeddingMalformedError(f"{where}: non-finite or non-numeric component")
    return [float(v) for v in values]


class EmbeddingProvider(ABC):
    """Authoritative embedding backend contract."""

    # -- identity -------------------------------------------------
    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable model identifier, e.g. sentence-transformers/all-MiniLM-L6-v2."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension; 0 only when the model is not loaded."""

    @property
    def normalized(self) -> bool:
        """True when vectors leave the provider L2-normalized."""
        return False

    @property
    def device(self) -> str:
        return "cpu"

    @property
    def test_only(self) -> bool:
        """True for deterministic test-grade providers (never production)."""
        return False

    # -- lifecycle ------------------------------------------------
    @abstractmethod
    def available(self) -> bool:
        """Real availability — never True merely because config exists."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """``{"status","available","model_id","dimension",...}``."""

    # -- inference ------------------------------------------------
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Embed one text; raises ``EmbeddingError`` on any failure."""

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch; default falls back to sequential ``embed``."""

    # -- shared helpers -------------------------------------------
    def as_embed_fn(self):
        """Adapt to the legacy ``Callable[[str], List[float]]`` seam."""
        return self.embed
