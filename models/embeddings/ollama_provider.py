from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Ollama Embedding Provider
Author: Heeran Paul
License: MIT
--------------------------------------------

Embedding provider over the existing Ollama stack. Availability is
honest: missing library, unreachable server, or unknown model all
report unavailable — never a silent hash fallback.
"""

from typing import Any, Dict, List

from models.embeddings.provider import (
    EmbeddingMalformedError,
    EmbeddingUnavailableError,
    EmbeddingProvider,
    validate_vector,
)


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama-hosted embedding models (e.g. nomic-embed-text)."""

    def __init__(self, model_id: str = "nomic-embed-text", host: str = "http://127.0.0.1:11434"):
        self._model_id = model_id
        self._host = host
        self._client: Any = None
        self._client_error = ""
        self._dimension = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return False  # server vectors used as-is; cosine scoring is scale-invariant

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import models.ollama.client as client_module

            if not getattr(client_module, "_HAS_OLLAMA", False):
                # The in-repo fallback stub fabricates hash vectors; it is
                # never acceptable as a production embedding source.
                raise EmbeddingUnavailableError(
                    "ollama library not installed; refusing stub vectors"
                )
            self._client = client_module.OllamaClient()
        except EmbeddingUnavailableError:
            raise
        except Exception as exc:
            self._client_error = str(exc)
            raise EmbeddingUnavailableError(f"ollama client unavailable: {exc}")
        return self._client

    def available(self) -> bool:
        try:
            client = self._client_or_raise()
            models = client.list_models() if hasattr(client, "list_models") else []
            names = [str(m) for m in models]
            if self._model_id not in names:
                # Either the model is absent or the backend cannot even
                # enumerate (stub/empty) — both mean "not verifiable".
                self._client_error = f"model '{self._model_id}' not confirmed on server"
                return False
            return True
        except EmbeddingUnavailableError:
            return False
        except Exception as exc:
            self._client_error = str(exc)
            return False

    def health(self) -> Dict[str, Any]:
        ok = self.available()
        return {
            "status": "healthy" if ok else "unavailable",
            "available": ok,
            "model_id": self._model_id,
            "dimension": self._dimension,
            "normalized": False,
            "device": "ollama-server",
            "test_only": False,
            "reason": "" if ok else self._client_error,
        }

    def embed(self, text: str) -> List[float]:
        if not isinstance(text, str):
            raise EmbeddingMalformedError(f"expected str, got {type(text).__name__}")
        client = self._client_or_raise()
        try:
            vector = client.embeddings(model=self._model_id, text=text)
        except Exception as exc:
            raise EmbeddingUnavailableError(f"ollama embedding failed for '{self._model_id}': {exc}")
        validated = validate_vector(list(vector), self._dimension or 0, "ollama-embed")
        self._dimension = len(validated)
        return validated

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Ollama serves one embedding per request; batching is sequential.
        return [self.embed(text) for text in texts]
