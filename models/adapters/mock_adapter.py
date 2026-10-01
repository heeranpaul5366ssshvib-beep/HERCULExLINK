from __future__ import annotations
"""Simple mock model adapter for local demos.

Provides naive embedding and chat functions for testing and demos without external models.
"""
from typing import List
import math

from models.adapters.base_adapter import BaseAdapter


class MockAdapter(BaseAdapter):
    def __init__(self, dim: int = 64):
        self.dim = dim

    def health(self):
        return {"status": "healthy", "available": True, "provider": "mock"}

    def _text_to_vector(self, text: str) -> List[float]:
        # deterministic hash-based pseudo-embedding
        vec = [0.0] * self.dim
        for tok in text.split():
            h = abs(hash(tok))
            idx = h % self.dim
            vec[idx] += (h % 1000) / 1000.0
        # normalize
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embeddings(self, model: str | None = None, text: str | None = None, texts: List[str] | None = None):
        if texts is not None:
            return [self._text_to_vector(t) for t in texts]
        if text is not None:
            return self._text_to_vector(text)
        if isinstance(model, list):
            return [self._text_to_vector(t) for t in model]
        raise TypeError("MockAdapter.embeddings() requires either `text` or `texts`.")

    def generate(self, prompt: str, model: str | None = None, **kwargs):
        return self.chat(model=model or "mock", prompt=prompt, **kwargs)

    def chat(self, model: str | None = None, prompt: str | None = None, system: str = "", context: List[str] | None = None, messages=None, **kwargs):
        if prompt is None and messages:
            prompt = messages[-1].get("content", "")
        ctx = "\n".join(context or [])
        if system:
            ctx = f"{system}\n{ctx}" if ctx else system
        return f"[MOCK ANSWER]\nPrompt: {prompt}\nContext:\n{ctx}\n"
